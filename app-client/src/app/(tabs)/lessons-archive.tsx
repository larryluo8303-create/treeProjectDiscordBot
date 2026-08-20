import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { api } from '../../api/client';

function useLessonArchive() {
  return useQuery({
    queryKey: ['public-lessons-archive'],
    queryFn: async () => {
      const resp = await api.get('/api/public/lessons/archive');
      return resp.data;
    },
    staleTime: 10 * 60 * 1000,
  });
}

export default function LessonsArchiveScreen() {
  const { data, isLoading, error } = useLessonArchive();

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
        <Text style={styles.errorText}>Failed to load lesson archive</Text>
      </View>
    );
  }

  const items: Array<{ title: string; content: string; scheduled_at: string }> =
    data?.items || [];

  if (items.length === 0) {
    return (
      <View style={styles.center}>
        <Ionicons name="school-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.emptyTitle}>No Past Lessons</Text>
        <Text style={styles.emptySubtitle}>Completed lessons will appear here</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>Lesson Archive</Text>
      <Text style={styles.subtitle}>{items.length} completed lesson{items.length !== 1 ? 's' : ''}</Text>

      {items.map((ls: { title: string; content: string; scheduled_at: string }, i: number) => (
        <View key={i} style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="school" size={16} color={Colors.info} />
            <Text style={styles.cardTitle}>{ls.title}</Text>
          </View>
          <Text style={styles.cardContent}>{ls.content}</Text>
          <View style={styles.cardFooter}>
            <Ionicons name="calendar-outline" size={14} color={Colors.textMuted} />
            <Text style={styles.cardDate}>
              {new Date(ls.scheduled_at).toLocaleDateString()}
            </Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: { color: Colors.text, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  subtitle: { color: Colors.textSecondary, fontSize: 13, marginBottom: 16 },
  errorText: { color: Colors.danger, fontSize: 16, marginTop: 12 },
  emptyTitle: { color: Colors.text, fontSize: 20, fontWeight: '700', marginTop: 16 },
  emptySubtitle: { color: Colors.textSecondary, fontSize: 14, marginTop: 8 },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  cardTitle: { color: Colors.text, fontSize: 15, fontWeight: '600', flex: 1 },
  cardContent: { color: Colors.textSecondary, fontSize: 13, lineHeight: 20, marginBottom: 8 },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  cardDate: { color: Colors.textMuted, fontSize: 12 },
});
