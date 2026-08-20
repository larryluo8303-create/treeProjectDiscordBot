/**
 * Dashboard screen — real-time status cards + recent query feed.
 */
import React from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useStats } from '../../api/stats';
import { usePendingReviews } from '../../api/review';
import { colors, confidenceColor } from '../../theme/colors';

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function timeAgo(timestamp: number): string {
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function DashboardScreen() {
  const { data: stats, isLoading, refetch } = useStats();
  const { data: reviews } = usePendingReviews();
  const [refreshing, setRefreshing] = React.useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
    >
      {/* Status cards */}
      <View style={styles.cardRow}>
        <View style={[styles.card, { borderLeftColor: colors.statusOnline }]}>
          <Text style={styles.cardLabel}>Uptime</Text>
          <Text style={styles.cardValue}>{formatUptime(stats?.uptime_seconds ?? 0)}</Text>
        </View>
        <View style={[styles.card, { borderLeftColor: colors.primary }]}>
          <Text style={styles.cardLabel}>Total Queries</Text>
          <Text style={styles.cardValue}>{stats?.total_queries ?? 0}</Text>
        </View>
      </View>

      <View style={styles.cardRow}>
        <View style={[styles.card, { borderLeftColor: colors.success }]}>
          <Text style={styles.cardLabel}>Auto Replies</Text>
          <Text style={styles.cardValue}>{stats?.auto_replies ?? 0}</Text>
        </View>
        <View style={[styles.card, { borderLeftColor: colors.warning }]}>
          <Text style={styles.cardLabel}>Pending Review</Text>
          <Text style={styles.cardValue}>{reviews?.count ?? 0}</Text>
        </View>
      </View>

      <View style={styles.cardRow}>
        <View style={[styles.card, { borderLeftColor: colors.info }]}>
          <Text style={styles.cardLabel}>Avg Confidence</Text>
          <Text style={styles.cardValue}>
            {stats?.avg_confidence !== undefined ? `${stats.avg_confidence.toFixed(1)}/10` : '-'}
          </Text>
        </View>
        <View style={[styles.card, { borderLeftColor: colors.textMuted }]}>
          <Text style={styles.cardLabel}>Avg Latency</Text>
          <Text style={styles.cardValue}>
            {stats?.avg_latency_ms !== undefined ? `${Math.round(stats.avg_latency_ms)}ms` : '-'}
          </Text>
        </View>
      </View>

      {/* Recent queries */}
      <Text style={styles.sectionTitle}>Recent Queries</Text>
      {(stats?.recent ?? []).length === 0 && (
        <Text style={styles.emptyText}>No recent queries</Text>
      )}
      {(stats?.recent ?? []).map((q, i) => (
        <View key={i} style={styles.queryItem}>
          <View style={styles.queryHeader}>
            <View style={[styles.badge, { backgroundColor: q.action === 'auto_reply' ? colors.success : colors.warning }]}>
              <Text style={styles.badgeText}>
                {q.action === 'auto_reply' ? 'Auto' : 'Fwd'}
              </Text>
            </View>
            <Text style={[styles.confidence, { color: confidenceColor(q.confidence) }]}>
              {q.confidence}/10
            </Text>
            <Text style={styles.timeAgo}>{timeAgo(q.timestamp)}</Text>
          </View>
          <Text style={styles.queryText} numberOfLines={2}>{q.question}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 32 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
  cardRow: { flexDirection: 'row', gap: 12, marginBottom: 12 },
  card: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 4,
  },
  cardLabel: { fontSize: 12, color: colors.textSecondary, marginBottom: 4 },
  cardValue: { fontSize: 22, fontWeight: '700', color: colors.textPrimary },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginTop: 20,
    marginBottom: 12,
  },
  emptyText: { color: colors.textMuted, textAlign: 'center', paddingVertical: 20 },
  queryItem: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
  },
  queryHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  badgeText: { fontSize: 11, fontWeight: '600', color: '#fff' },
  confidence: { fontSize: 13, fontWeight: '600' },
  timeAgo: { fontSize: 12, color: colors.textMuted, marginLeft: 'auto' },
  queryText: { fontSize: 14, color: colors.textSecondary, lineHeight: 20 },
});
