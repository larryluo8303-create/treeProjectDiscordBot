import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { useSummaries, SummaryItem } from '../../api/summaries';

type FilterType = 'all' | 'daily' | 'weekly';

export default function SummariesScreen() {
  const [filter, setFilter] = useState<FilterType>('all');
  const queryType = filter === 'all' ? undefined : filter;
  const { data, isLoading, error } = useSummaries(queryType);

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
        <Text style={styles.errorText}>Failed to load summaries</Text>
      </View>
    );
  }

  const items: SummaryItem[] = data?.items || [];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>Summaries</Text>
      <Text style={styles.subtitle}>AI-generated daily & weekly summaries</Text>

      {/* Filter buttons */}
      <View style={styles.filterRow}>
        {(['all', 'daily', 'weekly'] as const).map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.filterBtn, filter === t && styles.filterBtnActive]}
            onPress={() => setFilter(t)}
          >
            <Text style={[styles.filterText, filter === t && styles.filterTextActive]}>
              {t === 'all' ? 'All' : t === 'daily' ? 'Daily' : 'Weekly'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {items.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Ionicons name="document-text-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.emptyTitle}>No Summaries Yet</Text>
          <Text style={styles.emptySubtitle}>Summaries will appear here after they are generated</Text>
        </View>
      ) : (
        items.map((item: SummaryItem, i: number) => (
          <View key={i} style={styles.card}>
            <View style={styles.cardHeader}>
              <Ionicons
                name={item.type === 'daily' ? 'sunny' : 'calendar'}
                size={16}
                color={item.type === 'daily' ? Colors.warning : Colors.info}
              />
              <Text style={styles.cardTitle} numberOfLines={2}>{item.title}</Text>
              <View style={[styles.badge, item.type === 'daily' ? styles.badgeDaily : styles.badgeWeekly]}>
                <Text style={[styles.badgeText, item.type === 'daily' ? styles.badgeTextDaily : styles.badgeTextWeekly]}>
                  {item.type === 'daily' ? 'Daily' : 'Weekly'}
                </Text>
              </View>
            </View>

            <Text style={styles.cardContent}>{item.content}</Text>

            <View style={styles.cardFooter}>
              <View style={styles.footerItem}>
                <Ionicons name="calendar-outline" size={12} color={Colors.textMuted} />
                <Text style={styles.footerText}>
                  {new Date(item.timestamp).toLocaleString()}
                </Text>
              </View>
              <View style={styles.footerItem}>
                <Ionicons name="chatbubble-outline" size={12} color={Colors.textMuted} />
                <Text style={styles.footerText}>{item.message_count} msgs</Text>
              </View>
            </View>
          </View>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: { color: Colors.text, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  subtitle: { color: Colors.textSecondary, fontSize: 13, marginBottom: 12 },
  errorText: { color: Colors.danger, fontSize: 16, marginTop: 12 },
  emptyContainer: { alignItems: 'center', marginTop: 48 },
  emptyTitle: { color: Colors.text, fontSize: 20, fontWeight: '700', marginTop: 16 },
  emptySubtitle: { color: Colors.textSecondary, fontSize: 14, marginTop: 8, textAlign: 'center' },
  filterRow: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  filterBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterBtnActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  filterText: { color: Colors.textSecondary, fontSize: 13, fontWeight: '500' },
  filterTextActive: { color: '#fff' },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  cardTitle: { color: Colors.text, fontSize: 14, fontWeight: '600', flex: 1 },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  badgeDaily: { backgroundColor: Colors.warning + '33' },
  badgeWeekly: { backgroundColor: Colors.info + '33' },
  badgeText: { fontSize: 10, fontWeight: '700' },
  badgeTextDaily: { color: Colors.warning },
  badgeTextWeekly: { color: Colors.info },
  cardContent: { color: Colors.textSecondary, fontSize: 13, lineHeight: 20, marginBottom: 10 },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  footerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  footerText: { color: Colors.textMuted, fontSize: 11 },
});
