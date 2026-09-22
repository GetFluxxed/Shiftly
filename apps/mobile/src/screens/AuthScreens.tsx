import React, { useRef, useState } from 'react';
import { Redirect, useRouter } from 'expo-router';
import { TextInput, View } from 'react-native';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Brand, Button, Card, Column, Columns, Field, Heading, Loading, Notice, Screen, layout } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { colors } from '@/src/ui/theme';
import { useSensitiveForm } from '@/src/ui/useSensitiveForm';

export function SignInScreen() {
  const { status, signIn, message, busy } = useSession();
  const router = useRouter();
  const task = useTask();
  const [storeCode, setStoreCode] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const usernameInput = useRef<TextInput>(null);
  const passwordInput = useRef<TextInput>(null);
  useSensitiveForm(() => setPassword(''));
  if (status === 'ready' || status === 'locked') return <Redirect href="/today" />;
  if (status === 'loading') return <Loading label="Opening Shiftly…" />;
  const submit = () => { void task.run(async () => {
    const secret = password;
    setPassword('');
    await signIn({ storeCode: storeCode.trim(), username: username.trim(), password: secret });
  }); };
  return <Screen title="A better handoff.
A calmer shift." subtitle="Your people, your store, and everything the next shift needs to know.">
    <Brand />
    <Columns><Column><Card>
      <Heading>Welcome back</Heading><Body muted>Sign in with your individual account.</Body>
      <Notice message={task.error || message} kind={task.error ? 'error' : 'info'} />
      <Field label="Store code" value={storeCode} onChangeText={setStoreCode} autoCapitalize="none"
        autoCorrect={false} maxLength={120} placeholder="Your store code" returnKeyType="next"
        submitBehavior="submit" onSubmitEditing={() => usernameInput.current?.focus()} />
      <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none"
        autoCorrect={false} autoComplete="username" textContentType="username" maxLength={80}
        placeholder="Your username" returnKeyType="next" inputRef={usernameInput}
        submitBehavior="submit" onSubmitEditing={() => passwordInput.current?.focus()} />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry inputRef={passwordInput}
        autoCapitalize="none" autoCorrect={false} autoComplete="current-password" textContentType="password"
        maxLength={1024} returnKeyType="go" onSubmitEditing={submit} />
      <Button title="Sign in" icon="arrow-forward" onPress={submit} loading={task.pending || busy}
        disabled={!storeCode.trim() || !username.trim() || !password} />
      <Button title="Activate or recover an account" variant="quiet" onPress={() => router.push('/activate')} />
    </Card></Column>
    <Column><Card style={{ backgroundColor: colors.sage, borderColor: colors.sage }}>
      <Heading>Good shifts start with a clear picture.</Heading>
      <Body>Leave a useful handoff, catch up on your team's reports, and keep your store in sync.</Body>
      <View style={layout.divider} />
      <Body muted>New to the team? Ask your manager for an invitation code to set up your own account.</Body>
    </Card></Column></Columns>
  </Screen>;
}

export function ActivateScreen() {
  const { status, activate, resetPassword, busy } = useSession();
  const router = useRouter();
  const task = useTask();
  const [mode, setMode] = useState<'activate' | 'recover'>('activate');
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [complete, setComplete] = useState(false);
  const passwordInput = useRef<TextInput>(null);
  const confirmationInput = useRef<TextInput>(null);
  useSensitiveForm(() => { setToken(''); setPassword(''); setConfirmation(''); });
  if (status === 'ready' || status === 'locked') return <Redirect href="/today" />;
  if (status === 'loading') return <Loading />;
  const changeMode = (value: 'activate' | 'recover') => {
    setMode(value); setToken(''); setPassword(''); setConfirmation(''); setComplete(false); task.setError(null);
  };
  const submit = () => {
    if (password !== confirmation) { task.setError('Your passwords do not match.'); return; }
    void task.run(async () => {
      const credentials = { token: token.trim(), password };
      setPassword(''); setConfirmation(''); setToken('');
      await (mode === 'activate' ? activate(credentials) : resetPassword(credentials));
    }, () => setComplete(true));
  };
  return <Screen title={mode === 'activate' ? 'Make it yours.' : 'A fresh start.'} eyebrow="Your Shiftly account"
    subtitle="Use the private code given to you by your manager or account administrator.">
    <Columns><Column><Card>
      <View style={layout.wrap}>
        <Button title="Activate account" variant={mode === 'activate' ? 'primary' : 'secondary'} onPress={() => changeMode('activate')} disabled={task.pending || busy} />
        <Button title="Reset password" variant={mode === 'recover' ? 'primary' : 'secondary'} onPress={() => changeMode('recover')} disabled={task.pending || busy} />
      </View>
      {complete ? <><Notice kind="success" message={mode === 'activate' ? 'Your account is ready. Sign in with your store code and username.' : 'Your password has been reset. Sign in with your new password.'} />
        <Button title="Back to sign in" onPress={() => router.replace('/sign-in')} /></> : <>
        <Notice message={task.error} kind="error" />
        <Field label={mode === 'activate' ? 'Invitation code' : 'Recovery code'} value={token} onChangeText={setToken}
          autoCapitalize="none" autoCorrect={false} secureTextEntry maxLength={1024} returnKeyType="next"
          submitBehavior="submit" onSubmitEditing={() => passwordInput.current?.focus()} />
        <Field label="New password" value={password} onChangeText={setPassword} secureTextEntry
          autoCapitalize="none" autoCorrect={false} autoComplete="new-password" textContentType="newPassword" maxLength={1024}
          hint="Use at least 8 characters." inputRef={passwordInput} returnKeyType="next"
          submitBehavior="submit" onSubmitEditing={() => confirmationInput.current?.focus()} />
        <Field label="Confirm new password" value={confirmation} onChangeText={setConfirmation} secureTextEntry
          autoCapitalize="none" autoCorrect={false} autoComplete="new-password" textContentType="newPassword" maxLength={1024}
          returnKeyType="done" onSubmitEditing={submit} inputRef={confirmationInput} />
        <Button title={mode === 'activate' ? 'Activate my account' : 'Save new password'} onPress={submit}
          loading={task.pending || busy} disabled={!token.trim() || password.length < 8 || !confirmation} />
        <Button title="Back to sign in" variant="quiet" onPress={() => router.replace('/sign-in')} />
      </>}
    </Card></Column><Column><Card style={{ backgroundColor: colors.sage, borderColor: colors.sage }}>
      <Heading>A code just for you</Heading><Body>Codes can be used once and expire. If yours no longer works, ask {mode === 'activate' ? 'your manager' : 'your account administrator or operator'} for a replacement.</Body>
      <Body muted>Keep your code private. Your password belongs to you and is never shared with your team.</Body>
    </Card></Column></Columns>
  </Screen>;
}
