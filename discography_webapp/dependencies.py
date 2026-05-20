from services.logger import get_logger
from services.musicbrainz import MusicBrainzService
from services.soulseek import SoulseekService
from services.config import ConfigService
from services.queue import QueueService
from services.post_processor import PostProcessor
from services.orchestrator import Orchestrator

# Single-user mode
USER_ID = 1
orchestrators = {}

def get_orchestrator(event_bus, user_id: int = USER_ID):
    if user_id not in orchestrators:
        user_logger = get_logger(event_bus, user_id)
        mb_service = MusicBrainzService()
        config_service = ConfigService(user_id)
        # Restore real SoulseekService to preserve core functionality
        # The RustSoulseekService is currently a mock and breaks real downloads.
        slsk_service = SoulseekService()
        post_processor = PostProcessor(mb_service, config_service, user_logger)
        queue_service = QueueService(user_id)
        orchestrators[user_id] = Orchestrator(
            logger=user_logger, mb_service=mb_service, slsk_service=slsk_service,
            config_service=config_service, post_processor=post_processor,
            queue_service=queue_service, user_id=user_id
        )
    return orchestrators[user_id]
