import logging

LOGGER_NAME = "cyoa.game"
CHANNEL_SCENE = "scene"
CHANNEL_CHOICE = "choice"
CHANNEL_SYSTEM = "system"
CHANNEL_ENGINE = "engine"


class GameLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        channel = getattr(record, "game_channel", "game").upper()
        record.msg = f"[{channel}] {record.getMessage()}"
        record.args = ()
        return super().format(record)


def configure_game_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(GameLogFormatter("%(message)s"))
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = False
    return logger


class GameChannelAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("game_channel", self.extra["game_channel"])
        return msg, kwargs


def get_game_logger(channel: str = CHANNEL_SYSTEM) -> logging.LoggerAdapter:
    logger = logging.getLogger(LOGGER_NAME)
    return GameChannelAdapter(logger, {"game_channel": channel})
