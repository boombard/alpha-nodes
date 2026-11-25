"""Finance settings read from the environment; secrets and contact details are never committed."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class FinanceSettings(BaseSettings):
    """Environment-backed settings of the finance domain (prefix `ALPHA_NODES_`).

    Attributes:
        sec_user_agent: User-Agent SEC EDGAR requires, with contact details
            (`ALPHA_NODES_SEC_USER_AGENT`); None when unset, and the EDGAR provider factory then
            fails clearly. See documentation/design/finance.md, Providers.
    """

    model_config = SettingsConfigDict(env_prefix="ALPHA_NODES_", extra="ignore")

    sec_user_agent: str | None = None
