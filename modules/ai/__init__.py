from core.registry import registry, SubModule
from modules.ai.routes import ai_bp

registry.register_module(
    SubModule(
        key='ask_dipre',
        category_key='ai',
        title='Ask DIPRE (Flash & Pro)',
        blueprint=ai_bp,
    )
)
