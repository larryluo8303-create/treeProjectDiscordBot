import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { useKBSearch } from '../../api/kb';

export default function SearchScreen() {
  const [query, setQuery] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const { data, isLoading, error } = useKBSearch(searchTerm);

  const handleSearch = () => {
    const q = query.trim();
    if (q) setSearchTerm(q);
  };

  return (
    <View style={styles.container}>
      <View style={styles.searchBar}>
        <Ionicons name="search" size={20} color={Colors.textMuted} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search the knowledge base..."
          placeholderTextColor={Colors.textMuted}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
        />
      </View>

      {!searchTerm ? (
        <View style={styles.emptyState}>
          <Ionicons name="library-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.emptyTitle}>Knowledge Base Search</Text>
          <Text style={styles.emptySubtitle}>
            Search through historical posts, Q&A pairs, and documentation
          </Text>
        </View>
      ) : isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.primary} />
          <Text style={styles.searchingText}>Searching...</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Ionicons name="warning" size={48} color={Colors.danger} />
          <Text style={styles.errorText}>Search failed</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.results}>
          <Text style={styles.resultCount}>
            {data?.count || 0} results for "{searchTerm}"
          </Text>
          {(data?.results || []).map((r: { text: string; score: number; type: string }, i: number) => (
            <View key={i} style={styles.resultCard}>
              <View style={styles.resultHeader}>
                <View style={styles.typeBadge}>
                  <Text style={styles.typeText}>{r.type || 'doc'}</Text>
                </View>
                <Text style={styles.scoreText}>
                  {(r.score * 100).toFixed(0)}% match
                </Text>
              </View>
              <Text style={styles.resultText}>{r.text}</Text>
            </View>
          ))}
          {(data?.results || []).length === 0 && (
            <View style={styles.noResults}>
              <Ionicons name="search-outline" size={48} color={Colors.textMuted} />
              <Text style={styles.noResultsText}>No matching documents found</Text>
            </View>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    margin: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: 12,
  },
  searchIcon: { marginRight: 8 },
  searchInput: {
    flex: 1,
    color: Colors.text,
    fontSize: 15,
    paddingVertical: 12,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  emptyTitle: { color: Colors.text, fontSize: 20, fontWeight: '700', marginTop: 16 },
  emptySubtitle: { color: Colors.textSecondary, fontSize: 14, marginTop: 8, textAlign: 'center' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  searchingText: { color: Colors.textSecondary, fontSize: 14, marginTop: 12 },
  errorText: { color: Colors.danger, fontSize: 16, marginTop: 12 },
  results: { padding: 16, paddingTop: 0 },
  resultCount: { color: Colors.textSecondary, fontSize: 13, marginBottom: 12 },
  resultCard: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  resultHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  typeBadge: {
    backgroundColor: Colors.info + '22',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  typeText: { color: Colors.info, fontSize: 11, fontWeight: '600' },
  scoreText: { color: Colors.success, fontSize: 12, fontWeight: '600' },
  resultText: { color: Colors.textSecondary, fontSize: 13, lineHeight: 20 },
  noResults: { alignItems: 'center', marginTop: 40 },
  noResultsText: { color: Colors.textMuted, fontSize: 15, marginTop: 12 },
});
