import shlex

from . import utils as ut


logger = ut.get_logger(__name__)
SCRIPT_OK = 0
SCRIPT_ERROR = 1
SCRIPT_INTERRUPTED = 2


class Action:
    """One executable action inside an installer, uninstaller, or probe.

    Args:
        type: Action type, such as ``cmd``, ``patch_file``, or a package-manager
            adapter name.
        steps: Action payload normalized to a list of strings.
    """

    BUILTIN_ACTIONS: set[str] = {'cmd', 'patch_file'}

    def __init__(self, type: str, steps: list[str]):
        self._type = type
        self._steps = list(steps)

    @property
    def type(self) -> str:
        return self._type

    @property
    def steps(self) -> list[str]:
        return self._steps

    def __str__(self) -> str:
        preview = ' '.join(self._steps)[:10]
        return f"{self.type}({preview}...)"

    def __repr__(self) -> str:
        return f"<{self.type}(steps={len(self._steps)})>"

    def to_dict(self) -> dict[str, list[str]]:
        return {self.type: list(self.steps)}

    def execute(self, **kwargs) -> None:
        manager_map = kwargs['manager_map']
        operation = kwargs.get('operation', 'install')
        if self._type == 'cmd':
            for command in self._steps:
                logger.trace(f"cmd: {command}")
                ut.Shell.run(command)
            return
        if self._type == 'patch_file':
            logger.trace(f"patch_file: {self._steps[0]} {self._steps[1]}")
            ut.Files.patch_file(self._steps[0], self._steps[1], self._steps[2:], app_name=kwargs['app_name'])
            return
        if operation == 'uninstall':
            manager_map[self._type].uninstall(*self._steps)
            return
        manager_map[self._type].install(*self._steps)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        allowed_manager_actions: set[str] | None = None,
        allowed_builtin_actions: set[str] | None = None,
    ) -> 'Action':
        if len(data) != 1:
            raise ValueError('[-] Actions must define exactly one key')
        action_type, payload = next(iter(data.items()))
        builtin_actions = cls.BUILTIN_ACTIONS if allowed_builtin_actions is None else set(allowed_builtin_actions)
        allowed_actions = builtin_actions | set(allowed_manager_actions or ())
        if action_type not in allowed_actions:
            allowed = ', '.join(sorted(allowed_actions))
            raise ValueError(f"[-] Unknown action '{action_type}'. Allowed: {allowed}")
        return cls(action_type, cls._normalize_steps(action_type, payload))

    @staticmethod
    def _normalize_steps(action_type: str, payload) -> list[str]:
        if action_type == 'patch_file':
            if not isinstance(payload, list) or not all(isinstance(step, str) for step in payload):
                raise TypeError("[-] 'patch_file' expects a list of strings")
            if len(payload) < 3:
                raise ValueError("[-] 'patch_file' expects path, block_id and at least one line")
            return list(payload)
        if action_type == 'cmd':
            if isinstance(payload, str):
                return [payload]
            if isinstance(payload, list) and all(isinstance(step, str) for step in payload):
                return list(payload)
            raise TypeError("[-] 'cmd' expects a string or list of strings")
        if isinstance(payload, str):
            return shlex.split(payload)
        if isinstance(payload, list) and all(isinstance(step, str) for step in payload):
            return list(payload)
        raise TypeError(f"[-] '{action_type}' expects a string or list of strings")


class Script:
    """A named sequence of installer or uninstaller actions.

    Args:
        name: Script name, usually a platform or custom installer token.
        actions: Optional actions to execute in order.
    """

    def __init__(self, name: str, actions: list[Action] | None = None):
        self.name = name
        self._actions = list(actions or [])

    @property
    def actions(self) -> list[Action]:
        return self._actions

    def add_action(self, action: Action) -> None:
        self._actions.append(action)

    def to_data(self) -> list[dict[str, list[str]]]:
        return [action.to_dict() for action in self.actions]

    def run(
        self,
        *,
        app_name: str,
        manager_map: dict[str, object],
        operation: str = 'install',
        label: str | None = None,
    ) -> int:
        if label is None:
            label = 'uninstaller' if operation == 'uninstall' else 'installer'
        try:
            logger.info(f"Running {label} '{self.name}' for '{app_name}'")
            total = len(self._actions)
            for index, action in enumerate(self.actions, 1):
                logger.debug(f"({index}/{total}) {action.type}")
                action.execute(app_name=app_name, manager_map=manager_map, operation=operation)
            logger.success(f"{label.capitalize()} completed")
            return SCRIPT_OK
        except KeyboardInterrupt:
            logger.warning(f"{label.capitalize()} '{self.name}' interrupted by user")
            return SCRIPT_INTERRUPTED
        except Exception as exc:
            logger.exception(exc)
            return SCRIPT_ERROR

    @classmethod
    def from_data(
        cls,
        name: str,
        data: list[dict],
        allowed_manager_actions: set[str] | None = None,
    ) -> 'Script':
        if not isinstance(data, list):
            raise TypeError(f"[-] Installer '{name}' expects a list of actions")
        actions = [
            Action.from_dict(action, allowed_manager_actions=allowed_manager_actions)
            for action in data
        ]
        return cls(name=name, actions=actions)


class Probe:
    """A named read-only check used to detect installed applications.

    Args:
        name: Probe name, usually a manager or platform token.
        actions: Optional command actions to execute in order.
    """

    def __init__(self, name: str, actions: list[Action] | None = None):
        self.name = name
        self._actions = list(actions or [])

    @property
    def actions(self) -> list[Action]:
        return self._actions

    def add_action(self, action: Action) -> None:
        self._actions.append(action)

    def to_data(self) -> list[dict[str, list[str]]]:
        return [action.to_dict() for action in self.actions]

    def check(self) -> bool:
        try:
            for action in self.actions:
                action.execute(app_name=self.name, manager_map={})
        except Exception:
            return False
        return True

    @classmethod
    def from_data(cls, name: str, data: list[dict]) -> 'Probe':
        if not isinstance(data, list):
            raise TypeError(f"[-] Probe '{name}' expects a list of actions")
        actions = [
            Action.from_dict(action, allowed_builtin_actions={'cmd'})
            for action in data
        ]
        return cls(name=name, actions=actions)
