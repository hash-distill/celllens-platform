class CellLensError(RuntimeError):
    code = "CELLLENS_ERROR"


class RegistryError(CellLensError):
    code = "REGISTRY_ERROR"


class AssetNotReadyError(CellLensError):
    code = "ASSET_NOT_READY"


class StateInferenceError(CellLensError):
    code = "STATE_INFERENCE_FAILED"


class ScientificContractError(CellLensError):
    code = "SCIENTIFIC_CONTRACT_ERROR"


class InsufficientCoverageError(CellLensError):
    code = "INSUFFICIENT_METABOLIC_COVERAGE"


class InvalidTransitionError(CellLensError):
    code = "INVALID_RUN_TRANSITION"


class JobAlreadyClaimedError(CellLensError):
    code = "JOB_ALREADY_CLAIMED"
