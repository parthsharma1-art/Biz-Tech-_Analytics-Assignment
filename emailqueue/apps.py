import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

class EmailQueueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "emailqueue"

    def ready(self):
        # Gracefully create MongoDB indexes on application startup if connection is available
        try:
            from emailqueue.repositories.EmailRepository import EmailRepository
            repository = EmailRepository()
            repository.createIndexes()
            logger.info("MongoDB email collection indexes successfully verified.")
        except Exception as error:
            logger.debug("Deferred index creation until database is accessible: %s", str(error))

