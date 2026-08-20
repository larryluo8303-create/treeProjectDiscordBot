import { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Image,
  Linking,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { useNews, type NewsItem } from '../../api/news';

type Filter = 'all' | 'important';

export default function NewsScreen() {
  const { data, isLoading, error, refetch } = useNews(80);
  const [filter, setFilter] = useState<Filter>('all');
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

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
        <Text style={styles.errorText}>Failed to load market news</Text>
      </View>
    );
  }

  const allItems: NewsItem[] = data?.items ?? [];
  const items = filter === 'important' ? allItems.filter((n) => n.important) : allItems;

  const header = (
    <View style={styles.headerSection}>
      <Text style={styles.header}>Market News</Text>
      <Text style={styles.subtitle}>Real-time market flash news, auto-refreshing every 30s</Text>

      <View style={styles.filterRow}>
        <TouchableOpacity
          style={[styles.filterBtn, filter === 'all' && styles.filterBtnActive]}
          onPress={() => setFilter('all')}
        >
          <Text style={[styles.filterBtnText, filter === 'all' && styles.filterBtnTextActive]}>
            All
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.filterBtn, filter === 'important' && styles.filterBtnDanger]}
          onPress={() => setFilter('important')}
        >
          <Text style={[styles.filterBtnText, filter === 'important' && styles.filterBtnTextActive]}>
            Important
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  if (items.length === 0) {
    return (
      <View style={styles.container}>
        {header}
        <View style={styles.emptySection}>
          <Ionicons name="newspaper-outline" size={48} color={Colors.textMuted} />
          <Text style={styles.emptyText}>No news available</Text>
        </View>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={styles.content}
      data={items}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => <NewsCard item={item} />}
      ListHeaderComponent={header}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor={Colors.primary}
          colors={[Colors.primary]}
        />
      }
    />
  );
}

function NewsCard({ item }: { item: NewsItem }) {
  const [imgError, setImgError] = useState(false);

  return (
    <View style={[styles.card, item.important && styles.cardImportant]}>
      <View style={styles.cardRow}>
        {item.important && (
          <Ionicons name="star" size={16} color={Colors.danger} style={styles.starIcon} />
        )}
        <View style={styles.cardContent}>
          <Text style={[styles.cardTitle, item.important && styles.cardTitleImportant]}>
            {item.title}
          </Text>

          {item.body && item.body !== item.title ? (
            <Text style={styles.cardBody}>{item.body}</Text>
          ) : null}

          {item.pic && !imgError ? (
            <Image
              source={{ uri: item.pic }}
              style={styles.cardImage}
              resizeMode="contain"
              onError={() => setImgError(true)}
            />
          ) : null}

          <View style={styles.cardFooter}>
            <Text style={styles.cardTime}>{item.time}</Text>
            {item.link ? (
              <TouchableOpacity
                onPress={() => Linking.openURL(item.link!)}
                style={styles.linkBtn}
              >
                <Ionicons name="open-outline" size={12} color={Colors.primary} />
                <Text style={styles.linkText}>Details</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16, paddingBottom: 32 },
  headerSection: { marginBottom: 8 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: { color: Colors.text, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  subtitle: { color: Colors.textSecondary, fontSize: 13, marginBottom: 16 },
  errorText: { color: Colors.danger, fontSize: 16, marginTop: 12 },
  filterRow: {
    flexDirection: 'row',
    gap: 4,
    backgroundColor: Colors.surface,
    borderRadius: 10,
    padding: 3,
    marginBottom: 16,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterBtn: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 8,
  },
  filterBtnActive: {
    backgroundColor: Colors.primary,
  },
  filterBtnDanger: {
    backgroundColor: Colors.danger,
  },
  filterBtnText: {
    fontSize: 12,
    fontWeight: '600',
    color: Colors.textSecondary,
  },
  filterBtnTextActive: {
    color: '#FFFFFF',
  },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardImportant: {
    borderColor: 'rgba(239, 68, 68, 0.4)',
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  starIcon: {
    marginTop: 2,
  },
  cardContent: {
    flex: 1,
  },
  cardTitle: {
    color: Colors.text,
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
  },
  cardTitleImportant: {
    color: Colors.danger,
  },
  cardBody: {
    color: Colors.textSecondary,
    fontSize: 13,
    lineHeight: 19,
    marginTop: 4,
  },
  cardImage: {
    width: '100%',
    height: 180,
    borderRadius: 8,
    marginTop: 8,
  },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: 8,
  },
  cardTime: {
    color: Colors.textMuted,
    fontSize: 11,
  },
  linkBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  linkText: {
    color: Colors.primary,
    fontSize: 11,
  },
  emptySection: {
    alignItems: 'center',
    marginTop: 60,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: 15,
    marginTop: 12,
  },
});
