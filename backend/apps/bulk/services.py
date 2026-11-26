from django.db import transaction
from apps.common.logging import log_event
from django.utils import timezone
from .models import BulkBatch, BulkBatchRun, BulkBatchRunItem
from apps.tasks.models import Task
from apps.tasks.services.task_service import TaskService
from apps.clients.models import Client
from apps.periods.models import FinancialYear, Period

class BulkBatchService:
    @classmethod
    def resolve_clients(cls, batch: BulkBatch):
        """Resolves target clients based on client_selection."""
        firm = batch.firm
        selection = batch.client_selection or 'all'

        if selection == 'all':
            return Client.objects.filter(firm=firm)
        elif selection.startswith('group:'):
            group_id = selection.split(':')[1]
            return Client.objects.filter(firm=firm, client_group_id=group_id)
        elif selection.startswith('list:'):
            ids_str = selection.split('list:')[1].strip('[]')
            ids = [i.strip() for i in ids_str.split(',') if i.strip()]
            return Client.objects.filter(firm=firm, id__in=ids)
        return Client.objects.filter(firm=firm)

    @classmethod
    def preview_batch_run(cls, batch: BulkBatch, fy: FinancialYear, period: Period, user=None) -> BulkBatchRun:
        """
        Generates a PREVIEW run showing outcome for each candidate client
        WITHOUT creating tasks yet (§5.5 B1).
        """
        run = BulkBatchRun.objects.create(
            batch=batch,
            fy=fy,
            period=period,
            run_by=user,
            status=BulkBatchRun.Status.PREVIEW
        )

        clients = cls.resolve_clients(batch)
        items_to_create = []
        created_c = 0
        skipped_c = 0

        for client in clients:
            outcome = None
            msg = ''

            if not client.is_active:
                outcome = BulkBatchRunItem.Outcome.SKIPPED_INACTIVE
                msg = 'Client is deactivated'
                skipped_c += 1
            elif client.is_blocked_for_new_tasks:
                outcome = BulkBatchRunItem.Outcome.SKIPPED_BLOCKED
                msg = 'Client is blocked for new tasks'
                skipped_c += 1
            else:
                # Idempotency check: does task already exist for this (client, task_type, fy, period)?
                existing = Task.objects.filter(
                    client=client,
                    task_type=batch.task_type,
                    fy=fy,
                    period=period
                ).exclude(status=Task.Status.DELETED).first()

                if existing:
                    outcome = BulkBatchRunItem.Outcome.SKIPPED_DUPLICATE
                    msg = f"Task already exists: {existing.task_number}"
                    skipped_c += 1
                else:
                    outcome = BulkBatchRunItem.Outcome.CREATED
                    msg = 'Will be created on commit'
                    created_c += 1

            items_to_create.append(BulkBatchRunItem(
                run=run,
                client=client,
                outcome=outcome,
                message=msg
            ))

        BulkBatchRunItem.objects.bulk_create(items_to_create)
        run.created_count = created_c
        run.skipped_count = skipped_c
        run.save(update_fields=['created_count', 'skipped_count'])
        log_event('bulk.preview', 'BulkBatchRun', run.id, actor_user_id=getattr(user, 'id', None),
                  batch_id=batch.id, period=period.label, will_create=created_c, skipped=skipped_c)
        return run

    @classmethod
    def notify_admins(cls, batch, title, body='', actor=None):
        from apps.accounts.models import User
        from apps.notifications.models import Notification
        from apps.notifications.service import notify
        admins = User.objects.filter(firm=batch.firm, is_active=True, system_role__in=['superadmin', 'admin'])
        notify(Notification.Kind.BULK_RUN, list(admins), title, body=body, firm=batch.firm, actor=actor,
               link='/tasks?tile=pending')

    @classmethod
    def commit_batch_run(cls, run: BulkBatchRun, user=None) -> BulkBatchRun:
        """
        Commits a preview run: creates tasks for all items marked for creation.
        Uses one transaction per client (§5.12 K4).
        """
        with transaction.atomic():
            locked = BulkBatchRun.objects.select_for_update().get(pk=run.pk)
            if locked.status != BulkBatchRun.Status.PREVIEW:
                log_event('bulk.commit', 'BulkBatchRun', run.id, result='error', level='WARNING',
                          reason=f'run is {locked.status}, not preview')
                return locked
            # Mark as committed at once so a second click cannot start a parallel commit
            locked.status = BulkBatchRun.Status.COMMITTED
            locked.save(update_fields=['status'])
        batch = run.batch
        items = run.items.filter(outcome=BulkBatchRunItem.Outcome.CREATED)
        actual_created = 0
        error_count = 0

        for item in items:
            try:
                with transaction.atomic():
                    # Double check duplicate
                    existing = Task.objects.filter(
                        client=item.client,
                        task_type=batch.task_type,
                        fy=run.fy,
                        period=run.period
                    ).exclude(status=Task.Status.DELETED).first()

                    if existing:
                        item.outcome = BulkBatchRunItem.Outcome.SKIPPED_DUPLICATE
                        item.task = existing
                        item.message = f"Task already exists: {existing.task_number}"
                        item.save()
                        continue

                    task = TaskService.create_task(
                        firm=batch.firm,
                        branch=batch.branch,
                        client=item.client,
                        task_type=batch.task_type,
                        creator=user,
                        fy=run.fy,
                        period=run.period,
                        assigned_user=batch.default_assigned_user,
                        leader_user=batch.default_leader_user,
                        manager_user=batch.default_manager_user,
                        source=Task.Source.BULK,
                        bulk_batch_run_id=run.id
                    )
                    item.task = task
                    item.message = f"Created task: {task.task_number}"
                    item.save()
                    actual_created += 1
                    log_event('bulk.item', 'BulkBatchRun', run.id, client_id=item.client_id,
                              outcome='created', task_number=task.task_number)
            except Exception as e:  # noqa: BLE001 - one bad client must not stop the run (spec §5.12 K4)
                item.outcome = BulkBatchRunItem.Outcome.ERROR
                item.message = str(getattr(e, 'detail', e))[:255]
                item.save()
                error_count += 1
                log_event('bulk.item', 'BulkBatchRun', run.id, result='error', level='WARNING',
                          client_id=item.client_id, outcome='error', error=item.message)

        run.status = BulkBatchRun.Status.COMMITTED
        run.created_count = actual_created
        run.error_count = error_count
        run.run_at = timezone.now()
        run.save()
        log_event('bulk.commit', 'BulkBatchRun', run.id, actor_user_id=getattr(user, 'id', None),
                  batch_id=batch.id, period=run.period.label, created=actual_created, errors=error_count)
        cls.notify_admins(batch, f'Batch "{batch.name}" for {run.period.label} finished',
                          f'{actual_created} created, {run.skipped_count} skipped, {error_count} errors.', actor=user)
        return run
