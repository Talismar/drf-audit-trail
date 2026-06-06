from django.db import models

from .context import disable_manager_audit
from .entries import (
    schedule_create_entries,
    schedule_delete_entries,
    schedule_update_entries,
)
from .planning import (
    build_audit_plan,
    get_updated_tracked_fields,
    remove_reason_from_get_or_create_kwargs,
    validate_required_reason,
)
from .snapshots import (
    snapshot_by_pks,
    snapshot_existing_for_update_or_create,
    snapshot_object_identity,
    snapshot_queryset,
    snapshot_queryset_identity,
)
from .utils import get_instance_db, get_save_db


class AuditedQuerySet(models.QuerySet):
    def create(self, **kwargs):
        audit_plan = build_audit_plan(self.model, action="create", write_kwargs=kwargs)
        if not audit_plan.enabled:
            return super().create(**kwargs)

        validate_required_reason(audit_plan)
        kwargs = audit_plan.cleaned_write_kwargs
        with disable_manager_audit():
            obj = super().create(**kwargs)
        schedule_create_entries([obj], audit_plan, self.db)
        return obj

    def update(self, **kwargs):
        audit_plan = build_audit_plan(self.model, action="update", write_kwargs=kwargs)
        if not audit_plan.enabled:
            return super().update(**kwargs)

        kwargs = audit_plan.cleaned_write_kwargs
        tracked_fields = get_updated_tracked_fields(audit_plan, kwargs.keys())
        if not tracked_fields:
            return super().update(**kwargs)

        validate_required_reason(audit_plan)
        before = snapshot_queryset(self, audit_plan, fields=tracked_fields)
        updated_count = super().update(**kwargs)

        if before and tracked_fields:
            after = snapshot_by_pks(self.model, before.keys(), audit_plan, self.db)
            schedule_update_entries(before, after, audit_plan, self.db)

        return updated_count

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        audit_plan = build_audit_plan(self.model, action="create")
        if not audit_plan.enabled:
            return super().bulk_create(objs, *args, **kwargs)

        validate_required_reason(audit_plan)
        created_objs = super().bulk_create(objs, *args, **kwargs)
        if not kwargs.get("ignore_conflicts"):
            schedule_create_entries(created_objs, audit_plan, self.db)
        return created_objs

    def bulk_update(self, objs, fields, *args, **kwargs):
        objs = list(objs)
        audit_plan = build_audit_plan(self.model, action="update")
        if not audit_plan.enabled:
            return super().bulk_update(objs, fields, *args, **kwargs)

        tracked_fields = get_updated_tracked_fields(audit_plan, fields)
        if not tracked_fields:
            return super().bulk_update(objs, fields, *args, **kwargs)

        validate_required_reason(audit_plan)
        pks = [obj.pk for obj in objs if obj.pk is not None]
        before = snapshot_by_pks(self.model, pks, audit_plan, self.db, tracked_fields)
        with disable_manager_audit():
            updated_count = super().bulk_update(objs, fields, *args, **kwargs)

        if before and tracked_fields:
            after = snapshot_by_pks(self.model, before.keys(), audit_plan, self.db)
            schedule_update_entries(before, after, audit_plan, self.db)

        return updated_count

    def delete(self):
        audit_plan = build_audit_plan(self.model, action="delete")
        if not audit_plan.enabled:
            return super().delete()

        validate_required_reason(audit_plan)
        before = snapshot_queryset_identity(self)
        result = super().delete()
        schedule_delete_entries(before, audit_plan, self.db)
        return result

    def get_or_create(self, defaults=None, **kwargs):
        defaults = defaults.copy() if defaults else {}
        write_kwargs = {**kwargs, **defaults}
        audit_plan = build_audit_plan(
            self.model,
            action="create",
            write_kwargs=write_kwargs,
            mutate_write_kwargs=False,
        )
        if not audit_plan.enabled:
            return super().get_or_create(defaults=defaults, **kwargs)

        kwargs, defaults = remove_reason_from_get_or_create_kwargs(
            self.model, kwargs, defaults, audit_plan.reason_field
        )
        validate_required_reason(audit_plan)

        with disable_manager_audit():
            obj, created = super().get_or_create(defaults=defaults, **kwargs)
        if audit_plan.enabled and created:
            schedule_create_entries([obj], audit_plan, self.db)
        return obj, created

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        defaults = defaults.copy() if defaults else {}
        create_defaults = create_defaults.copy() if create_defaults else None
        write_kwargs = {**kwargs, **defaults}
        if create_defaults:
            write_kwargs.update(create_defaults)

        audit_plan = build_audit_plan(
            self.model,
            action="update",
            write_kwargs=write_kwargs,
            mutate_write_kwargs=False,
        )
        if not audit_plan.enabled:
            if create_defaults is None:
                return super().update_or_create(defaults=defaults, **kwargs)
            return super().update_or_create(
                defaults=defaults,
                create_defaults=create_defaults,
                **kwargs,
            )

        before = {}
        kwargs, defaults = remove_reason_from_get_or_create_kwargs(
            self.model, kwargs, defaults, audit_plan.reason_field
        )
        if create_defaults is not None:
            _, create_defaults = remove_reason_from_get_or_create_kwargs(
                self.model, {}, create_defaults, audit_plan.reason_field
            )
        before = snapshot_existing_for_update_or_create(
            self.model, kwargs, audit_plan, self.db
        )
        validate_required_reason(audit_plan)

        if create_defaults is None:
            with disable_manager_audit():
                obj, created = super().update_or_create(defaults=defaults, **kwargs)
        else:
            with disable_manager_audit():
                obj, created = super().update_or_create(
                    defaults=defaults,
                    create_defaults=create_defaults,
                    **kwargs,
                )

        if created:
            create_plan = audit_plan.with_action("create")
            schedule_create_entries([obj], create_plan, self.db)
        elif before:
            after = snapshot_by_pks(self.model, before.keys(), audit_plan, self.db)
            schedule_update_entries(before, after, audit_plan, self.db)

        return obj, created


class AuditedManager(models.Manager.from_queryset(AuditedQuerySet)):
    pass


class AuditedModel(models.Model):
    objects = AuditedManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        is_create = self._state.adding
        action = "create" if is_create else "update"
        audit_plan = build_audit_plan(self.__class__, action=action)
        if not audit_plan.enabled:
            return super().save(*args, **kwargs)

        using = get_save_db(self, kwargs)
        before = {}
        tracked_update_fields = None

        if is_create:
            validate_required_reason(audit_plan)
        else:
            update_fields = kwargs.get("update_fields")
            tracked_update_fields = (
                get_updated_tracked_fields(audit_plan, update_fields)
                if update_fields is not None
                else audit_plan.fields
            )
            if tracked_update_fields:
                validate_required_reason(audit_plan)
                before = snapshot_existing_for_update_or_create(
                    self.__class__,
                    {self._meta.pk.name: self.pk},
                    audit_plan,
                    using,
                    fields=tracked_update_fields,
                )

        result = super().save(*args, **kwargs)

        if is_create:
            schedule_create_entries([self], audit_plan, get_instance_db(self))
        elif before and tracked_update_fields:
            after = snapshot_by_pks(
                self.__class__,
                before.keys(),
                audit_plan,
                get_instance_db(self),
                fields=tracked_update_fields,
            )
            schedule_update_entries(before, after, audit_plan, get_instance_db(self))

        return result

    def delete(self, *args, **kwargs):
        audit_plan = build_audit_plan(self.__class__, action="delete")
        if not audit_plan.enabled:
            return super().delete(*args, **kwargs)

        validate_required_reason(audit_plan)
        using = kwargs.get("using") or get_instance_db(self)
        before = {self.pk: snapshot_object_identity(self)}
        result = super().delete(*args, **kwargs)
        schedule_delete_entries(before, audit_plan, using)
        return result
