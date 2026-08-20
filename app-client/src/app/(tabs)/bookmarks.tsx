import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, confidenceColor } from '../../theme/colors';
import { loadBookmarks, deleteBookmark, type Bookmark } from '../../utils/storage';

export default function BookmarksScreen() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);

  useFocusEffect(
    useCallback(() => {
      loadBookmarks().then(setBookmarks);
    }, [])
  );

  const handleDelete = (id: string) => {
    Alert.alert('Delete Bookmark', 'Remove this saved answer?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          deleteBookmark(id).then(() => {
            setBookmarks((prev: Bookmark[]) => prev.filter((b: Bookmark) => b.id !== id));
          });
        },
      },
    ]);
  };

  if (bookmarks.length === 0) {
    return (
      <View style={styles.center}>
        <Ionicons name="bookmark-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.emptyTitle}>No Bookmarks</Text>
        <Text style={styles.emptySubtitle}>
          Tap the bookmark icon on any bot answer to save it here
        </Text>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      data={bookmarks}
      keyExtractor={(item: Bookmark) => item.id}
      contentContainerStyle={styles.content}
      renderItem={({ item }: { item: Bookmark }) => (
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="help-circle-outline" size={16} color={Colors.primary} />
            <Text style={styles.question} numberOfLines={2}>{item.question}</Text>
            <TouchableOpacity onPress={() => handleDelete(item.id)}>
              <Ionicons name="trash-outline" size={16} color={Colors.danger} />
            </TouchableOpacity>
          </View>
          <Text style={styles.answer}>{item.answer}</Text>
          <View style={styles.cardFooter}>
            <View style={[styles.confBadge, { backgroundColor: confidenceColor(item.confidence) + '22' }]}>
              <Text style={[styles.confText, { color: confidenceColor(item.confidence) }]}>
                {item.confidence}/10
              </Text>
            </View>
            <Text style={styles.dateText}>
              {new Date(item.savedAt).toLocaleDateString()}
            </Text>
          </View>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
    padding: 32,
  },
  emptyTitle: { color: Colors.text, fontSize: 20, fontWeight: '700', marginTop: 16 },
  emptySubtitle: { color: Colors.textSecondary, fontSize: 14, marginTop: 8, textAlign: 'center' },
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
  question: { color: Colors.text, fontSize: 14, fontWeight: '600', flex: 1 },
  answer: { color: Colors.textSecondary, fontSize: 13, lineHeight: 20, marginBottom: 8 },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  confBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  confText: { fontSize: 11, fontWeight: '700' },
  dateText: { color: Colors.textMuted, fontSize: 11 },
});
