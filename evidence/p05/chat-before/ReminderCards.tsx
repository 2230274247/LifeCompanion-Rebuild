import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@librechat/client';
import { QueryKeys, lifeService } from 'librechat-data-provider';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { LifeReminderDraft, LifeDraftFields } from 'librechat-data-provider';
import { useAuthContext, useLocalize } from '~/hooks';
import Provisioning from './Provisioning';
import useLifeMode from './useLifeMode';
import ChatSources from './ChatSources';

function ReminderCard({
  draft,
  onSaved,
}: {
  draft: LifeReminderDraft;
  onSaved: (draft: LifeReminderDraft) => void;
}) {
  const localize = useLocalize();
  const [fields, setFields] = useState<LifeDraftFields>(() => ({
    title: draft.title,
    event_date: draft.event_date,
    event_time: draft.event_time?.slice(0, 5) ?? null,
    timezone: draft.timezone,
    lead_minutes: draft.lead_minutes,
    place: draft.place,
  }));
  const [review, setReview] = useState(false);
  const [editKnown, setEditKnown] = useState(false);
  const [other, setOther] = useState(false);
  const [choiceValue, setChoiceValue] = useState('');
  const choose = useMutation(
    (value: string) =>
      lifeService.selectReminderDraft(draft.draft_id, draft.revision, {
        [draft.quick_choice?.field ?? 'event_time']: value,
      }),
    {
      onSuccess: (value) => {
        onSaved(value);
        setEditKnown(false);
        setOther(false);
      },
    },
  );
  const save = useMutation(
    () => lifeService.selectReminderDraft(draft.draft_id, draft.revision, fields),
    {
      onSuccess: (value) => {
        onSaved(value);
        setReview(value.status === 'ready_to_confirm');
      },
    },
  );
  const confirm = useMutation(
    () => lifeService.confirmReminderDraft(draft.draft_id, draft.revision),
    {
      onSuccess: onSaved,
    },
  );
  const cancel = useMutation(() => lifeService.cancelReminderDraft(draft.draft_id), {
    onSuccess: onSaved,
  });
  const reconcile = useMutation(() => lifeService.reconcileReminderDraft(draft.draft_id), {
    onSuccess: onSaved,
  });
  const pending =
    choose.isLoading ||
    save.isLoading ||
    confirm.isLoading ||
    cancel.isLoading ||
    reconcile.isLoading;
  const error = choose.error ?? save.error ?? confirm.error ?? cancel.error ?? reconcile.error;
  const code =
    error && typeof error === 'object' && 'response' in error
      ? (error as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail
          ?.code
      : null;
  const inputClass =
    'min-h-11 w-full rounded-lg border border-border-medium bg-surface-primary px-3 text-text-primary';
  const displayTime = (value: string) =>
    new Intl.DateTimeFormat('zh-CN', {
      dateStyle: 'full',
      timeStyle: 'short',
      timeZone: draft.timezone ?? 'UTC',
    }).format(new Date(value));
  const terminal = [
    'scheduled',
    'unknown',
    'creating',
    'cancelled',
    'completed',
    'expired',
  ].includes(draft.status);
  if (draft.reference_options) {
    return (
      <section
        aria-label={localize('com_life_draft_reference')}
        className="my-4 max-w-xl space-y-3 rounded-2xl border border-border-medium bg-surface-primary-alt p-4"
        data-testid="reminder-reference-card"
      >
        <h3 className="font-serif text-xl">{localize('com_life_draft_reference')}</h3>
        <p className="text-sm text-text-secondary">{localize('com_life_draft_reference_hint')}</p>
        {draft.reference_options.length === 0 ? (
          <p>{localize('com_life_draft_reference_empty')}</p>
        ) : (
          draft.reference_options.map((option) => (
            <a
              key={option.draft_id}
              href={`#${encodeURIComponent(option.source_message_id)}`}
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(option.source_message_id)?.scrollIntoView({
                  behavior: 'smooth',
                  block: 'start',
                });
              }}
              className="flex min-h-11 items-center rounded-lg border border-border-medium px-3 py-2 text-link underline"
            >
              {option.title ?? localize('com_life_reminder_title')} · {option.event_date} ·{' '}
              {option.event_time ?? localize('com_life_draft_clock')}
            </a>
          ))
        )}
      </section>
    );
  }
  return (
    <section
      aria-label={localize('com_life_draft_heading')}
      className="my-4 max-w-xl space-y-4 rounded-2xl border border-border-medium bg-surface-primary-alt p-4 sm:p-5"
      data-testid="reminder-draft-card"
      data-source-message-id={draft.source_message_id}
    >
      <h3 className="font-serif text-xl">{localize('com_life_draft_heading')}</h3>
      <p className="break-words text-sm text-text-secondary">
        {draft.title ?? localize('com_life_reminder_title')} · {draft.place} · {draft.timezone}
      </p>
      {draft.status === 'scheduled' && draft.reminder ? (
        <div role="status" className="space-y-2">
          <p>
            {localize('com_life_reminder_created')} · {displayTime(draft.reminder.scheduled_at)}
          </p>
          <p className="break-all text-sm">
            {localize('com_life_draft_receipt')}: {draft.reminder.reminder_id} /{' '}
            {draft.reminder.upstream_task_id}
          </p>
          <p className="text-sm text-text-secondary">{localize('com_life_draft_delivery')}</p>
          <Link
            className="inline-flex min-h-11 items-center text-link underline"
            to={`/reminders/${draft.reminder.reminder_id}`}
          >
            {localize('com_life_view_reminder')}
          </Link>
          <Button
            className="ml-3 min-h-11"
            variant="outline"
            disabled={pending}
            onClick={() => cancel.mutate()}
          >
            {localize('com_life_reminder_cancel')}
          </Button>
        </div>
      ) : null}
      {draft.status === 'unknown' || draft.status === 'creating' ? (
        <div role="status" className="space-y-3">
          <p>{localize('com_life_draft_unknown')}</p>
          <Button className="min-h-11" disabled={pending} onClick={() => reconcile.mutate()}>
            {localize('com_life_draft_reconcile')}
          </Button>
          <Link
            className="inline-flex min-h-11 items-center px-3 text-link underline"
            to="/reminders"
          >
            {localize('com_life_reminders')}
          </Link>
        </div>
      ) : null}
      {draft.status === 'cancelled' || draft.status === 'expired' ? (
        <p role="status">
          {localize(
            draft.status === 'cancelled'
              ? 'com_life_reminder_cancelled_status'
              : 'com_life_draft_expired',
          )}
        </p>
      ) : null}
      {draft.status === 'cancelled' && draft.reminder ? (
        <Link
          className="inline-flex min-h-11 items-center text-link underline"
          to={`/reminders/${draft.reminder.reminder_id}`}
        >
          {localize('com_life_view_reminder')}
        </Link>
      ) : null}
      {!terminal ? (
        <>
          <Provisioning availability={draft.availability} />
          {draft.quick_choice ? (
            <div className="space-y-3">
              <p>
                {localize(
                  draft.quick_choice.field === 'event_date'
                    ? 'com_life_choose_date'
                    : 'com_life_choose_time',
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                {draft.quick_choice.options.map((option) => (
                  <Button
                    key={option.value}
                    variant="outline"
                    className="min-h-11 rounded-full"
                    disabled={pending}
                    onClick={() => choose.mutate(option.value)}
                  >
                    {option.label}
                  </Button>
                ))}
                <Button
                  variant="ghost"
                  className="min-h-11"
                  disabled={pending}
                  onClick={() => setOther(true)}
                >
                  {localize('com_life_other_choice')}
                </Button>
              </div>
              {other ? (
                <form
                  className="flex flex-wrap gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    choose.mutate(choiceValue);
                  }}
                >
                  <label>
                    {localize(
                      draft.quick_choice.field === 'event_date'
                        ? 'com_life_draft_date'
                        : 'com_life_draft_clock',
                    )}
                    <input
                      type={draft.quick_choice.other}
                      required
                      className={inputClass}
                      value={choiceValue}
                      onChange={(event) => setChoiceValue(event.target.value)}
                    />
                  </label>
                  <Button type="submit" disabled={pending || !choiceValue}>
                    {localize('com_life_choose_save')}
                  </Button>
                </form>
              ) : null}
              <p className="text-sm text-text-secondary">{localize('com_life_choose_hint')}</p>
              <Button variant="ghost" disabled={pending} onClick={() => cancel.mutate()}>
                {localize('com_life_reminder_cancel')}
              </Button>
            </div>
          ) : (review || draft.missing_fields.length === 0) && draft.preview && !editKnown ? (
            <div className="space-y-3" aria-live="polite">
              <p>
                {localize('com_life_draft_event_at')}: {displayTime(draft.preview.event_at)}
              </p>
              <p className="font-medium">
                {localize('com_life_draft_remind_at')}: {displayTime(draft.preview.scheduled_at)}
              </p>
              <p className="text-sm text-text-secondary">{localize('com_life_draft_train_note')}</p>
              <div className="flex flex-wrap gap-3">
                <Button
                  className="min-h-11"
                  variant="outline"
                  disabled={pending}
                  onClick={() => setEditKnown(true)}
                >
                  {localize('com_life_draft_edit')}
                </Button>
                <Button
                  className="min-h-11"
                  disabled={pending || draft.availability.status !== 'ready'}
                  onClick={() => confirm.mutate()}
                >
                  {localize('com_life_draft_confirm')}
                </Button>
              </div>
            </div>
          ) : (
            <form
              className="grid gap-4 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (!pending) {
                  save.mutate();
                }
              }}
              onKeyDown={(event) => {
                if (event.nativeEvent.isComposing && event.key === 'Enter') {
                  event.preventDefault();
                }
              }}
            >
              {editKnown || !draft.title ? (
                <label className="grid gap-2 sm:col-span-2">
                  {localize('com_life_reminder_title')}
                  <input
                    className={inputClass}
                    required
                    maxLength={200}
                    value={fields.title ?? ''}
                    onChange={(event) => setFields({ ...fields, title: event.target.value })}
                  />
                </label>
              ) : null}
              {editKnown || !draft.event_date || draft.error_code === 'REMINDER_TIME_IN_PAST' ? (
                <label className="grid gap-2">
                  {localize('com_life_draft_date')}
                  <input
                    className={inputClass}
                    required
                    type="date"
                    value={fields.event_date ?? ''}
                    onChange={(event) => setFields({ ...fields, event_date: event.target.value })}
                  />
                </label>
              ) : null}
              {editKnown || !draft.event_time || Boolean(draft.error_code) ? (
                <label className="grid gap-2">
                  {localize('com_life_draft_clock')}
                  <input
                    className={inputClass}
                    required
                    type="time"
                    value={fields.event_time ?? ''}
                    onChange={(event) => setFields({ ...fields, event_time: event.target.value })}
                  />
                </label>
              ) : null}
              {editKnown || draft.lead_minutes == null ? (
                <label className="grid gap-2">
                  {localize('com_life_draft_lead')}
                  <select
                    className={inputClass}
                    required
                    value={fields.lead_minutes ?? ''}
                    onChange={(event) =>
                      setFields({ ...fields, lead_minutes: Number(event.target.value) })
                    }
                  >
                    <option value="" disabled>
                      {localize('com_life_draft_select')}
                    </option>
                    {Array.from(
                      new Set([
                        0,
                        10,
                        30,
                        60,
                        120,
                        ...(fields.lead_minutes == null ? [] : [fields.lead_minutes]),
                      ]),
                    ).map((minutes) => (
                      <option key={minutes} value={minutes}>
                        {minutes} {localize('com_life_draft_minutes')}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              {editKnown || !draft.timezone || draft.error_code === 'INVALID_TIMEZONE' ? (
                <label className="grid gap-2">
                  {localize('com_life_draft_timezone')}
                  <input
                    className={inputClass}
                    required
                    value={fields.timezone ?? ''}
                    onChange={(event) => setFields({ ...fields, timezone: event.target.value })}
                  />
                </label>
              ) : null}
              <p className="text-sm text-text-secondary sm:col-span-2">
                {localize('com_life_draft_train_note')}
              </p>
              <div className="flex flex-wrap gap-3 sm:col-span-2">
                <Button className="min-h-11" type="submit" disabled={pending}>
                  {localize('com_life_draft_next')}
                </Button>
                <Button
                  className="min-h-11"
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => cancel.mutate()}
                >
                  {localize('com_life_reminder_cancel')}
                </Button>
              </div>
            </form>
          )}
        </>
      ) : null}
      {error ? (
        <p role="alert" className="break-words">
          {localize('com_life_draft_error')} {code}
        </p>
      ) : null}
      {draft.error_code ? <p role="alert">{draft.error_code}</p> : null}
    </section>
  );
}

export default function ReminderCards({
  conversationId,
  sourceMessageId,
  isSubmitting,
}: {
  conversationId?: string | null;
  sourceMessageId?: string | null;
  isSubmitting?: boolean;
}) {
  const { user } = useAuthContext();
  const lifeMode = useLifeMode();
  const localize = useLocalize();
  const cache = useQueryClient();
  const key = [QueryKeys.lifeReminderDrafts, user?.id, conversationId];
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => lifeService.reminderDrafts(conversationId ?? '', signal),
    enabled: Boolean(
      lifeMode && user?.id && conversationId && conversationId !== 'new' && sourceMessageId,
    ),
    refetchInterval: (data) =>
      isSubmitting || data?.drafts.some((draft) => draft.availability.status === 'provisioning')
        ? 1500
        : false,
    retry: false,
  });
  const onSaved = (value: LifeReminderDraft) => {
    cache.setQueryData<{ drafts: LifeReminderDraft[] }>(key, (old) => ({
      drafts: (old?.drafts ?? []).map((item) => (item.draft_id === value.draft_id ? value : item)),
    }));
    void cache.invalidateQueries([QueryKeys.lifeReminders, user?.id]);
  };
  if (!lifeMode || !sourceMessageId) {
    return null;
  }
  return (
    <>
      {conversationId ? (
        <ChatSources
          conversationId={conversationId}
          sourceMessageId={sourceMessageId}
          isSubmitting={isSubmitting}
        />
      ) : null}
      {query.isError ? (
        <p role="alert">
          {localize('com_life_draft_load_error')}{' '}
          <Button className="min-h-11" onClick={() => void query.refetch()}>
            {localize('com_ui_retry')}
          </Button>
        </p>
      ) : null}
      {query.data?.drafts
        .filter((item) => item.source_message_id === sourceMessageId)
        .map((draft) => (
          <ReminderCard key={`${user?.id}:${draft.draft_id}`} draft={draft} onSaved={onSaved} />
        ))}
    </>
  );
}
