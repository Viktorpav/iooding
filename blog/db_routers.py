class AIRouter:
    """
    A router to control all database operations on models in the
    AI specific database.
    """
    route_app_labels = {'blog'}

    def db_for_read(self, model, **hints):
        if model._meta.model_name == 'postchunk':
            return 'ai'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.model_name == 'postchunk':
            return 'ai'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations if neither object is PostChunk
        if obj1._meta.model_name == 'postchunk' or obj2._meta.model_name == 'postchunk':
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name == 'postchunk':
            return db == 'ai'
        if db == 'ai':
            return False
        return None
