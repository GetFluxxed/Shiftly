import React from 'react';
import { useRouter } from 'expo-router';
import { headsUpPath, headsUpSaveUncertain, type HeadsUp } from './api';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, EmptyState, Field, Heading, Loading, Notice, Screen } from '@/src/ui/components';
import { friendlyDate } from '@/src/ui/theme';
import { useResource } from '@/src/ui/useResource';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';

export function HeadsUpScreen() {
  const { actor, request, busy } = useSession();
  const router = useRouter();
  const allowed = actor?.role === 'manager' || actor?.role === 'crew' || actor?.role === 'production';
  const canEdit = actor?.role === 'manager';
  const resource = useResource<HeadsUp>(headsUpPath, allowed);
  const back = () => router.replace(canEdit ? '/store' : '/today');

  if (!allowed) return <Screen title="Heads Up" eyebrow="Store update">
    <Button title="Back to Today" icon="arrow-back" variant="quiet" onPress={() => router.replace('/today')} />
    <Card><Heading>Heads Up is unavailable</Heading><Body>This update is for store managers, production, and crew members.</Body></Card>
  </Screen>;

  return <Screen title={canEdit ? 'Keep your team in the loop.' : 'Heads Up'} eyebrow="Store update"
    subtitle={canEdit ? 'Share one clear update for everyone working at this store.' : 'The latest note from your manager.'}>
    <Button title={canEdit ? 'Back to Store' : 'Back to Today'} icon="arrow-back" variant="quiet" onPress={back} />
    {resource.loading ? <Card><Loading label="Getting the latest update…" /></Card> : resource.error ? <Card>
      <Notice message={resource.error} kind="error" /><Button title="Retry update" variant="secondary" onPress={() => { void resource.refresh(); }} />
    </Card> : resource.data ? <HeadsUpContent current={resource.data} canEdit={canEdit} busy={busy}
      request={request} refresh={resource.refresh} /> : null}
  </Screen>;
}

function HeadsUpContent({ current, canEdit, busy, request, refresh }: {
  current: HeadsUp; canEdit: boolean; busy: boolean;
  request: ReturnType<typeof useSession>['request']; refresh: () => Promise<void>;
}) {
  const task = useTask();
  const baseline = `${current.updatedAt || ''}\n${current.message}`;
  const [editor, setEditor, resetEditor] = useRememberedState('heads-up.editor',
    { editing: false, draft: '' }, baseline);
  const beginEdit = () => { setEditor({ editing: true, draft: current.message || '' }); task.setError(null); };
  const cancel = () => { resetEditor(); task.setError(null); };
  const save = () => {
    const message = editor.draft.trim();
    if (!message) return;
    void task.run(async () => {
      const saved = await request<HeadsUp>(headsUpPath, {
        method: 'POST', body: { message }, uncertainMessage: headsUpSaveUncertain,
      });
      resetEditor();
      return saved;
    }, () => { void refresh(); });
  };
  return editor.editing && canEdit ? <Card>
      <Heading>{current.message ? 'Edit Heads Up' : 'Create Heads Up'}</Heading>
      <Field label="Message" value={editor.draft} onChangeText={draft => setEditor(value => ({ ...value, draft }))} multiline maxLength={1000} editable={!task.pending && !busy}
        placeholder="What does the team need to know for this shift?" hint={`${editor.draft.length} / 1,000 characters`} />
      <Notice message={task.error} kind="error" />
      {editor.draft !== current.message ? <Notice message="You have an unsaved change." /> : null}
      <Button title="Save Heads Up" icon="checkmark-outline" loading={task.pending || busy} disabled={!editor.draft.trim()} onPress={save} />
      <Button title="Cancel" variant="quiet" disabled={task.pending || busy} onPress={cancel} />
      <Body muted>This draft is saved securely on this device until you save or cancel it.</Body>
    </Card> : <Card>
      <Heading>Current update</Heading>
      {current.message ? <>
        <Body>{current.message}</Body>
        {current.updatedAt ? <Body muted>Updated {friendlyDate(current.updatedAt)}</Body> : null}
      </> : <EmptyState icon="chatbubble-ellipses-outline" title="All clear for now"
        description={canEdit ? 'There is no store update. Create one when your team needs a quick heads up.' : 'There are no store updates to show right now.'} />}
      {canEdit ? <Button title={current.message ? 'Edit Heads Up' : 'Create Heads Up'} icon="create-outline" onPress={beginEdit} /> : null}
      <Button title="Refresh update" variant="secondary" icon="refresh-outline" onPress={() => { void refresh(); }} />
    </Card>;
}
