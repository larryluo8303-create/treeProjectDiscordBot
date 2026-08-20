/**
 * Config screen — view and edit runtime bot configuration.
 */
import React, { useState, useEffect } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TextInput, Switch,
  TouchableOpacity, Alert, ActivityIndicator,
} from 'react-native';
import { useConfig, usePatchConfig, type BotConfig } from '../../api/config';
import { colors } from '../../theme/colors';

export default function ConfigScreen() {
  const { data, isLoading } = useConfig();
  const patchMut = usePatchConfig();
  const [draft, setDraft] = useState<Partial<BotConfig>>({});

  useEffect(() => {
    if (data) {
      setDraft({
        confidence_threshold: data.confidence_threshold,
        respond_mode: data.respond_mode,
        user_cooldown_seconds: data.user_cooldown_seconds,
        global_max_per_minute: data.global_max_per_minute,
        thread_auto_reply: data.thread_auto_reply,
        thread_context_messages: data.thread_context_messages,
        conversation_memory_size: data.conversation_memory_size,
        conversation_memory_ttl: data.conversation_memory_ttl,
      });
    }
  }, [data]);

  const save = () => {
    patchMut.mutate(draft, {
      onSuccess: () => Alert.alert('Saved', 'Configuration updated (runtime only).'),
      onError: (err: any) => Alert.alert('Error', err?.message || 'Failed to save'),
    });
  };

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Read-only info */}
      <Text style={styles.section}>Models</Text>
      <View style={styles.readOnly}>
        <Text style={styles.roLabel}>LLM</Text>
        <Text style={styles.roValue}>{data?.llm_model}</Text>
      </View>
      <View style={styles.readOnly}>
        <Text style={styles.roLabel}>Embedding</Text>
        <Text style={styles.roValue}>{data?.embedding_model}</Text>
      </View>
      <View style={styles.readOnly}>
        <Text style={styles.roLabel}>Vision</Text>
        <Text style={styles.roValue}>{data?.vision_model}</Text>
      </View>

      {/* Editable fields */}
      <Text style={styles.section}>Response Settings</Text>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Respond Mode</Text>
        <TextInput
          style={styles.fieldInput}
          value={draft.respond_mode ?? ''}
          onChangeText={(v) => setDraft((d) => ({ ...d, respond_mode: v }))}
        />
      </View>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Confidence Threshold</Text>
        <TextInput
          style={styles.fieldInput}
          value={String(draft.confidence_threshold ?? '')}
          onChangeText={(v) => setDraft((d) => ({ ...d, confidence_threshold: parseInt(v) || 0 }))}
          keyboardType="number-pad"
        />
      </View>

      <Text style={styles.section}>Rate Limiting</Text>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>User Cooldown (s)</Text>
        <TextInput
          style={styles.fieldInput}
          value={String(draft.user_cooldown_seconds ?? '')}
          onChangeText={(v) => setDraft((d) => ({ ...d, user_cooldown_seconds: parseInt(v) || 0 }))}
          keyboardType="number-pad"
        />
      </View>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Global Max/min</Text>
        <TextInput
          style={styles.fieldInput}
          value={String(draft.global_max_per_minute ?? '')}
          onChangeText={(v) => setDraft((d) => ({ ...d, global_max_per_minute: parseInt(v) || 0 }))}
          keyboardType="number-pad"
        />
      </View>

      <Text style={styles.section}>Thread Settings</Text>
      <View style={styles.switchRow}>
        <Text style={styles.fieldLabel}>Thread Auto Reply</Text>
        <Switch
          value={draft.thread_auto_reply ?? false}
          onValueChange={(v) => setDraft((d) => ({ ...d, thread_auto_reply: v }))}
          trackColor={{ false: colors.border, true: colors.primary }}
        />
      </View>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Thread Context Messages</Text>
        <TextInput
          style={styles.fieldInput}
          value={String(draft.thread_context_messages ?? '')}
          onChangeText={(v) => setDraft((d) => ({ ...d, thread_context_messages: parseInt(v) || 0 }))}
          keyboardType="number-pad"
        />
      </View>

      <Text style={styles.section}>Conversation Memory</Text>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Memory Size</Text>
        <TextInput
          style={styles.fieldInput}
          value={String(draft.conversation_memory_size ?? '')}
          onChangeText={(v) => setDraft((d) => ({ ...d, conversation_memory_size: parseInt(v) || 0 }))}
          keyboardType="number-pad"
        />
      </View>
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Memory TTL (s)</Text>
        <TextInput
          style={styles.fieldInput}
          value={String(draft.conversation_memory_ttl ?? '')}
          onChangeText={(v) => setDraft((d) => ({ ...d, conversation_memory_ttl: parseInt(v) || 0 }))}
          keyboardType="number-pad"
        />
      </View>

      <TouchableOpacity style={styles.saveBtn} onPress={save} disabled={patchMut.isPending}>
        <Text style={styles.saveBtnText}>
          {patchMut.isPending ? 'Saving...' : 'Save Changes'}
        </Text>
      </TouchableOpacity>

      <Text style={styles.note}>Changes are runtime only and will reset on bot restart.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
  section: { fontSize: 16, fontWeight: '600', color: colors.textPrimary, marginTop: 20, marginBottom: 10 },
  readOnly: {
    flexDirection: 'row', justifyContent: 'space-between',
    backgroundColor: colors.surface, borderRadius: 8, padding: 12, marginBottom: 6,
  },
  roLabel: { fontSize: 13, color: colors.textSecondary },
  roValue: { fontSize: 13, color: colors.textPrimary, fontWeight: '500' },
  field: { marginBottom: 10 },
  fieldLabel: { fontSize: 13, color: colors.textSecondary, marginBottom: 4 },
  fieldInput: {
    backgroundColor: colors.surface, borderRadius: 8, paddingHorizontal: 12,
    paddingVertical: 10, color: colors.textPrimary, fontSize: 14,
    borderWidth: 1, borderColor: colors.border,
  },
  switchRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 10,
  },
  saveBtn: {
    backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 14,
    alignItems: 'center', marginTop: 24,
  },
  saveBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  note: { fontSize: 12, color: colors.textMuted, textAlign: 'center', marginTop: 10 },
});
