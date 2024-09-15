from drf_audit_trail.settings import DRF_AUDIT_TRAIL_DATABASE_ALIAS


class DRFAuditTrail:
    """
    A router to control all database operations on models in the
    drf_audit_trail application.
    """

    route_app_labels = {"drf_audit_trail"}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return DRF_AUDIT_TRAIL_DATABASE_ALIAS
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return DRF_AUDIT_TRAIL_DATABASE_ALIAS
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label in self.route_app_labels or (
            obj2._meta.app_label in self.route_app_labels
        ):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.route_app_labels:
            return db == DRF_AUDIT_TRAIL_DATABASE_ALIAS

        return None
