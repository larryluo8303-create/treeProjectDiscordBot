import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { useDigest } from '../../api/digest';

export default function DigestScreen() {
  const { data, isLoading, error, refetch } = useDigest();

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Ionicons name="warning" size={48} color={Colors.danger} />
        <Text style={styles.errorText}>Failed to load digest</Text>
      </View>
    );
  }

  const total = data?.total_queries ?? 0;
  const autoReplies = data?.auto_replies ?? 0;
  const avgConf = data?.avg_confidence ?? 0;
  const topQuestions: string[] = data?.top_questions ?? [];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>Daily Digest</Text>
      <Text style={styles.subtitle}>Last 24 hours activity summary</Text>

      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Ionicons name="chatbubbles-outline" size={24} color={Colors.primary} />
          <Text style={styles.statValue}>{total}</Text>
          <Text style={styles.statLabel}>Queries</Text>
        </View>
        <View style={styles.statCard}>
          <Ionicons name="flash-outline" size={24} color={Colors.success} />
          <Text style={styles.statValue}>{autoReplies}</Text>
          <Text style={styles.statLabel}>Auto Replies</Text>
        </View>
        <View style={styles.statCard}>
          <Ionicons name="analytics-outline" size={24} color={Colors.warning} />
          <Text style={styles.statValue}>{avgConf}</Text>
          <Text style={styles.statLabel}>Avg Confidence</Text>
        </View>
      </View>

      {topQuestions.length > 0 && (
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Ionicons name="trending-up" size={20} color={Colors.info} />
            <Text style={styles.sectionTitle}>Top Questions</Text>
          </View>
          {topQuestions.map((q: string, i: number) => (
            <View key={i} style={styles.questionItem}>
              <Text style={styles.questionNumber}>{i + 1}</Text>
              <Text style={styles.questionText}>{q}</Text>
            </View>
          ))}
        </View>
      )}

      {total === 0 && (
        <View style={styles.emptySection}>
          <Ionicons name="moon-outline" size={48} color={Colors.textMuted} />
          <Text style={styles.emptyText}>No activity in the last 24 hours</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: { color: Colors.text, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  subtitle: { color: Colors.textSecondary, fontSize: 13, marginBottom: 20 },
  errorText: { color: Colors.danger, fontSize: 16, marginTop: 12 },
  statsRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  statCard: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 6,
  },
  statValue: { color: Colors.text, fontSize: 24, fontWeight: '700' },
  statLabel: { color: Colors.textSecondary, fontSize: 11 },
  section: { marginBottom: 20 },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  sectionTitle: { color: Colors.text, fontSize: 18, fontWeight: '700' },
  questionItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: Colors.surface,
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  questionNumber: {
    color: Colors.primary,
    fontSize: 14,
    fontWeight: '700',
    width: 24,
    textAlign: 'center',
  },
  questionText: { color: Colors.text, fontSize: 14, flex: 1, lineHeight: 20 },
  emptySection: {
    alignItems: 'center',
    marginTop: 40,
  },
  emptyText: { color: Colors.textMuted, fontSize: 15, marginTop: 12 },
});
