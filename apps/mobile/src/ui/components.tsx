import { Text, useFontsReady } from '@/src/ui/Typography';
import React, { PropsWithChildren, createContext, useCallback, useContext, useRef } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, TextInput, TextInputProps, View, ViewStyle, useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { colors, fonts } from './theme';

const ScrollContext = createContext<() => void>(() => undefined);
export function useScrollToTop() { return useContext(ScrollContext); }

export function Screen({ children, title, eyebrow, subtitle, trailing }: PropsWithChildren<{
  title: string; eyebrow?: string; subtitle?: string; trailing?: React.ReactNode;
}>) {
  const { width } = useWindowDimensions();
  const scroll = useRef<ScrollView>(null);
  const toTop = useCallback(() => { scroll.current?.scrollTo({ y: 0, animated: false }); }, []);
  return <SafeAreaView edges={['top', 'left', 'right']} style={styles.safe}>
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView ref={scroll} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
        contentContainerStyle={[styles.scroll, { paddingHorizontal: width >= 768 ? 36 : 22 }]}>
        <View style={styles.container}>
          <View style={styles.header}>
            <View style={styles.flex}>
              <View accessible={false} style={styles.headerAccent} />
              {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
              <Text accessibilityRole="header" style={styles.title}>{title}</Text>
              {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
            </View>
            {trailing}
          </View>
          <ScrollContext.Provider value={toTop}>{children}</ScrollContext.Provider>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}

export function Brand() {
  return <View style={styles.brandRow} accessibilityLabel="Shiftly">
    <View style={styles.brandMark}><Ionicons name="sunny-outline" color={colors.primary} size={24} /></View>
    <Text style={styles.brand}>shiftly<Text style={{ color: colors.accentStrong, fontFamily: fonts.display }}>.</Text></Text>
  </View>;
}

export function Card({ children, style }: PropsWithChildren<{ style?: ViewStyle }>) {
  return <View style={[styles.card, style]}>{children}</View>;
}
export function Heading({ children }: PropsWithChildren) {
  return <Text accessibilityRole="header" style={styles.heading}>{children}</Text>;
}
export function Body({ children, muted = false }: PropsWithChildren<{ muted?: boolean }>) {
  return <Text style={[styles.body, muted && { color: colors.muted }]}>{children}</Text>;
}
export function Eyebrow({ children }: PropsWithChildren) {
  return <Text style={styles.eyebrow}>{children}</Text>;
}
export function Columns({ children }: PropsWithChildren) {
  const { width, fontScale } = useWindowDimensions();
  return <View style={[styles.columns, width >= 900 && fontScale < 1.5 && { flexDirection: 'row' }]}>{children}</View>;
}
export function Column({ children }: PropsWithChildren) {
  const { width, fontScale } = useWindowDimensions();
  return <View style={[styles.column, width >= 900 && fontScale < 1.5 ? { flex: 1 } : { flexGrow: 0, flexShrink: 0 }]}>{children}</View>;
}

export function Button({ title, onPress, variant = 'primary', loading = false, disabled = false, icon }: {
  title: string; onPress: () => void; variant?: 'primary' | 'secondary' | 'quiet' | 'danger';
  loading?: boolean; disabled?: boolean; icon?: React.ComponentProps<typeof Ionicons>['name'];
}) {
  const foreground = variant === 'primary' ? colors.onPrimary : variant === 'danger' ? colors.danger : colors.primary;
  return <Pressable accessibilityRole="button" accessibilityLabel={title}
    accessibilityState={{ disabled: disabled || loading, busy: loading }} disabled={disabled || loading}
    onPress={onPress} style={({ pressed }) => [styles.button,
      variant === 'primary' ? styles.primary : variant === 'secondary' ? styles.secondary : variant === 'danger' ? styles.danger : styles.quiet,
      (disabled || loading) && { opacity: 0.55 }, pressed && { opacity: 0.75 }]}>
    {loading ? <ActivityIndicator color={foreground} /> : icon ? <Ionicons name={icon} size={20} color={foreground} /> : null}
    <Text style={[styles.buttonText, { color: foreground }]}>{title}</Text>
  </Pressable>;
}

export function Field({ label, hint, inputRef, ...props }: TextInputProps & { label: string; hint?: string; inputRef?: React.Ref<TextInput> }) {
  const fontsReady = useFontsReady();
  return <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput ref={inputRef} accessibilityLabel={label} placeholderTextColor={colors.muted} selectionColor={colors.accentStrong}
      {...props} style={[styles.input, props.multiline && styles.multiline, props.style, { fontFamily: fontsReady ? fonts.body : undefined }]} />
    {hint ? <Text style={styles.hint}>{hint}</Text> : null}
  </View>;
}

export function Notice({ message, kind = 'info' }: { message: string | null; kind?: 'info' | 'error' | 'success' }) {
  if (!message) return null;
  const error = kind === 'error';
  const foreground = error ? colors.danger : kind === 'success' ? colors.success : colors.primary;
  return <View style={[styles.notice, { backgroundColor: error ? colors.dangerPaper : kind === 'success' ? colors.successPaper : colors.soft }]}
    accessibilityRole={error ? 'alert' : undefined} accessibilityLiveRegion="polite">
    <Ionicons name={error ? 'alert-circle-outline' : kind === 'success' ? 'checkmark-circle-outline' : 'information-circle-outline'}
      size={21} color={foreground} />
    <Text style={[styles.noticeText, { color: foreground }]}>{message}</Text>
  </View>;
}

export function EmptyState({ icon, title, description }: {
  icon: React.ComponentProps<typeof Ionicons>['name']; title: string; description: string;
}) {
  return <View style={styles.empty}>
    <View style={styles.emptyIcon}><Ionicons name={icon} color={colors.primary} size={34} /></View>
    <Heading>{title}</Heading><Body muted>{description}</Body>
  </View>;
}

export function Loading({ label = 'Loading your workspace…' }: { label?: string }) {
  return <View style={styles.loading} accessibilityLiveRegion="polite">
    <ActivityIndicator color={colors.primary} size="large" /><Body muted>{label}</Body>
  </View>;
}

export function Pill({ label }: { label: string }) {
  return <View style={styles.pill}><Text style={styles.pillText}>{label}</Text></View>;
}

export const layout = StyleSheet.create({
  gap: { gap: 16 }, smallGap: { gap: 10 }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, flex: { flex: 1, minWidth: 0 },
  divider: { height: 1, backgroundColor: colors.line, marginVertical: 4 },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.paper }, flex: { flex: 1, minWidth: 0 },
  scroll: { paddingTop: 22, paddingBottom: 36, flexGrow: 1 },
  container: { width: '100%', maxWidth: 1160, alignSelf: 'center', gap: 22 },
  headerAccent: { width: 44, height: 4, borderRadius: 2, backgroundColor: colors.accent, marginBottom: 18 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 12 },
  eyebrow: { fontSize: 12, fontWeight: '700', letterSpacing: 1.6, textTransform: 'uppercase', color: colors.primary, marginBottom: 10 },
  title: { fontFamily: fonts.display, fontSize: 40, lineHeight: 43, letterSpacing: -0.8, color: colors.ink },
  subtitle: { fontSize: 16, lineHeight: 24, color: colors.muted, marginTop: 12, maxWidth: 620 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12 },
  brandMark: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.blush, alignItems: 'center', justifyContent: 'center' },
  brand: { fontFamily: fonts.display, fontSize: 36, letterSpacing: -1, color: colors.ink },
  card: { borderWidth: 1, borderColor: colors.line, backgroundColor: colors.card, borderRadius: 20, padding: 22, gap: 16 },
  heading: { fontFamily: fonts.display, fontSize: 25, lineHeight: 30, letterSpacing: -0.3, color: colors.ink, flexShrink: 1 },
  body: { fontSize: 16, lineHeight: 25, color: colors.ink },
  columns: { gap: 22 }, column: { minWidth: 0, gap: 22 },
  button: { minHeight: 52, borderRadius: 27, paddingVertical: 14, paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  primary: { backgroundColor: colors.primary }, secondary: { borderColor: colors.controlLine, borderWidth: 1, backgroundColor: colors.soft },
  danger: { borderColor: colors.danger, borderWidth: 1, backgroundColor: colors.dangerPaper },
  quiet: { backgroundColor: 'transparent' }, buttonText: { fontWeight: '700', fontSize: 16, flexShrink: 1, textAlign: 'center' },
  field: { gap: 8 }, label: { fontSize: 14, fontWeight: '600', color: colors.ink },
  input: { minHeight: 54, paddingHorizontal: 16, paddingVertical: 14, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.white, borderRadius: 12, color: colors.ink, fontSize: 16 },
  multiline: { minHeight: 180, textAlignVertical: 'top', lineHeight: 25 }, hint: { fontSize: 13, lineHeight: 20, color: colors.muted },
  notice: { padding: 15, borderRadius: 14, backgroundColor: colors.soft, flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  noticeText: { flex: 1, fontSize: 14, lineHeight: 22, color: colors.primary },
  empty: { alignItems: 'flex-start', justifyContent: 'center', gap: 15, minHeight: 230, paddingVertical: 18 },
  emptyIcon: { width: 68, height: 68, borderRadius: 22, backgroundColor: colors.blush, justifyContent: 'center', alignItems: 'center', marginBottom: 4 },
  loading: { padding: 36, alignItems: 'center', justifyContent: 'center', gap: 20, flex: 1, backgroundColor: colors.paper },
  pill: { backgroundColor: colors.blush, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7, alignSelf: 'flex-start' },
  pillText: { fontSize: 12, lineHeight: 18, fontWeight: '700', color: colors.primary, textTransform: 'capitalize' },
});
