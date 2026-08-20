/**
 * More screen — FAQ management, digest, and logout.
 */
import React from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, Alert, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useFAQ, useGenerateFAQ } from '../../api/faq';
import { logout } from '../../api/auth';
import { wsManager } from '../../api/ws';
import { colors } from '../../theme/colors';

export default function MoreScreen() {
  const router = useRouter();
  const { data: faqData, isLoading: faqLoading } = useFAQ();
  const generateFAQ = useGenerateFAQ();

  const handleGenerateFAQ = () => {
    Alert.alert(
      'Generate FAQ',
      'This will regenerate FAQ from recent high-confidence queries. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Generate', onPress: () => generateFAQ.mutate() },
      ],
    );
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Disconnect from the bot server?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout',
        style: 'destructive',
        onPress: () => {
          wsManager.disconnect();
          logout();
          router.replace('/login');
        },
      },
    ]);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* FAQ section */}
      <Text style={styles.section}>FAQ</Text>
      <TouchableOpacity
        style={styles.actionBtn}
        onPress={handleGenerateFAQ}
        disabled={generateFAQ.isPending}
      >
        <Text style={styles.actionBtnText}>
          {generateFAQ.isPending ? 'Generating...' : 'Regenerate FAQ'}
        </Text>
      </TouchableOpacity>

      {faqLoading ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 12 }} />
      ) : (
        (faqData?.items ?? []).map((item, i) => (
          <View key={i} style={styles.faqCard}>
            <Text style={styles.faqQ}>Q: {item.question}</Text>
            <Text style={styles.faqA}>A: {item.answer}</Text>
          </View>
        ))
      )}

      {(faqData?.items ?? []).length === 0 && !faqLoading && (
        <Text style={styles.emptyText}>No FAQ items yet. Generate them above.</Text>
      )}

      {/* Logout */}
      <Text style={styles.section}>Account</Text>
      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Text style={styles.logoutBtnText}>Logout</Text>
      </TouchableOpacity>

      <Text style={styles.version}>BigTree Bot App v1.0.0</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 40 },
  section: { fontSize: 16, fontWeight: '600', color: colors.textPrimary, marginTop: 20, marginBottom: 10 },
  actionBtn: {
    backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 12, alignItems: 'center',
  },
  actionBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  faqCard: {
    backgroundColor: colors.surface, borderRadius: 10, padding: 14, marginTop: 8,
  },
  faqQ: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: 6 },
  faqA: { fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
  emptyText: { color: colors.textMuted, textAlign: 'center', marginTop: 16 },
  logoutBtn: {
    backgroundColor: colors.danger, borderRadius: 8, paddingVertical: 12, alignItems: 'center',
  },
  logoutBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  version: { color: colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: 24 },
});
