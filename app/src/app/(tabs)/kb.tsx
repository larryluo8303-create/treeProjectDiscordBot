/**
 * Knowledge Base screen — search and browse KB documents.
 */
import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TextInput, ActivityIndicator,
} from 'react-native';
import { useKBInfo, useKBSearch } from '../../api/kb';
import { colors } from '../../theme/colors';

export default function KBScreen() {
  const { data: info } = useKBInfo();
  const [query, setQuery] = useState('');
  const { data: results, isFetching } = useKBSearch(query);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.infoRow}>
        <Text style={styles.infoLabel}>Documents</Text>
        <Text style={styles.infoValue}>{info?.count ?? '-'}</Text>
      </View>

      <TextInput
        style={styles.searchInput}
        value={query}
        onChangeText={setQuery}
        placeholder="Search knowledge base..."
        placeholderTextColor={colors.textMuted}
        returnKeyType="search"
      />

      {isFetching && (
        <ActivityIndicator style={{ marginTop: 20 }} color={colors.primary} />
      )}

      {results && results.count > 0 && (
        <Text style={styles.resultCount}>{results.count} result(s)</Text>
      )}

      {results?.results.map((r, i) => (
        <View key={i} style={styles.resultCard}>
          <View style={styles.resultHeader}>
            <View style={styles.typeBadge}>
              <Text style={styles.typeBadgeText}>
                {r.metadata?.type || 'doc'}
              </Text>
            </View>
            <Text style={styles.distance}>
              dist: {r.distance.toFixed(3)}
            </Text>
          </View>
          <Text style={styles.resultText}>{r.text}</Text>
        </View>
      ))}

      {query.length === 0 && info?.samples && info.samples.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Sample Documents</Text>
          {info.samples.map((s, i) => (
            <View key={i} style={styles.sampleCard}>
              <View style={styles.typeBadge}>
                <Text style={styles.typeBadgeText}>{s.type}</Text>
              </View>
              <Text style={styles.sampleText} numberOfLines={3}>{s.text}</Text>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 32 },
  infoRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    backgroundColor: colors.surface, borderRadius: 10, padding: 14, marginBottom: 12,
  },
  infoLabel: { fontSize: 14, color: colors.textSecondary },
  infoValue: { fontSize: 18, fontWeight: '700', color: colors.textPrimary },
  searchInput: {
    backgroundColor: colors.surface, borderRadius: 10, paddingHorizontal: 14,
    paddingVertical: 12, color: colors.textPrimary, fontSize: 15,
    borderWidth: 1, borderColor: colors.border, marginBottom: 8,
  },
  resultCount: { fontSize: 13, color: colors.textMuted, marginTop: 8, marginBottom: 8 },
  resultCard: {
    backgroundColor: colors.surface, borderRadius: 10, padding: 14, marginBottom: 8,
  },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  typeBadge: {
    backgroundColor: colors.primaryDark, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4,
  },
  typeBadgeText: { fontSize: 11, fontWeight: '600', color: '#fff' },
  distance: { fontSize: 12, color: colors.textMuted },
  resultText: { fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: colors.textPrimary, marginTop: 16, marginBottom: 10 },
  sampleCard: {
    backgroundColor: colors.surface, borderRadius: 10, padding: 14, marginBottom: 8,
  },
  sampleText: { fontSize: 13, color: colors.textSecondary, marginTop: 6, lineHeight: 18 },
});
