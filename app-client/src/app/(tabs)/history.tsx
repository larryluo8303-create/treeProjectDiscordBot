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
import { Colors } from '../../theme/colors';
import { loadSessions, deleteSession, type ChatSession } from '../../utils/storage';

export default function HistoryScreen() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  useFocusEffect(
    useCallback(() => {
      loadSessions().then(setSessions);
    }, [])
  );

  const handleDelete = (id: string) => {
    Alert.alert('Delete Conversation', 'Remove this chat session?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          deleteSession(id).then(() => {
            setSessions((prev: ChatSession[]) => prev.filter((s: ChatSession) => s.id !== id));
          });
        },
      },
    ]);
  };

  if (sessions.length === 0) {
    return (
      <View style={styles.center}>
        <Ionicons name="time-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.emptyTitle}>No Chat History</Text>
        <Text style={styles.emptySubtitle}>
          Your past conversations will appear here
        </Text>
      </View>
    );
  }

  const groupedByDate: Record<string, ChatSession[]> = {};
  sessions.forEach((s: ChatSession) => {
    const dateKey = new Date(s.updatedAt).toLocaleDateString();
    if (!groupedByDate[dateKey]) groupedByDate[dateKey] = [];
    groupedByDate[dateKey].push(s);
  });

  type ListItem =
    | { type: 'header'; date: string }
    | { type: 'session'; session: ChatSession };

  const listData: ListItem[] = [];
  Object.entries(groupedByDate).forEach(([date, items]: [string, ChatSession[]]) => {
    listData.push({ type: 'header', date });
    items.forEach((session: ChatSession) => {
      listData.push({ type: 'session', session });
    });
  });

  return (
    <FlatList
      style={styles.container}
      data={listData}
      keyExtractor={(_item: ListItem, i: number) => String(i)}
      contentContainerStyle={styles.content}
      renderItem={({ item }: { item: ListItem }) => {
        if (item.type === 'header') {
          return <Text style={styles.dateHeader}>{item.date}</Text>;
        }
        const s = item.session;
        const msgCount = s.messages.length;
        return (
          <View style={styles.card}>
            <View style={styles.cardContent}>
              <Ionicons name="chatbubble-outline" size={16} color={Colors.primary} />
              <View style={styles.cardText}>
                <Text style={styles.sessionTitle} numberOfLines={1}>{s.title}</Text>
                <Text style={styles.sessionMeta}>
                  {msgCount} message{msgCount !== 1 ? 's' : ''} ·{' '}
                  {new Date(s.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Text>
              </View>
              <TouchableOpacity onPress={() => handleDelete(s.id)}>
                <Ionicons name="close-circle-outline" size={20} color={Colors.textMuted} />
              </TouchableOpacity>
            </View>
          </View>
        );
      }}
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
  dateHeader: {
    color: Colors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
    marginTop: 12,
    marginBottom: 8,
  },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  cardText: { flex: 1 },
  sessionTitle: { color: Colors.text, fontSize: 14, fontWeight: '600' },
  sessionMeta: { color: Colors.textMuted, fontSize: 11, marginTop: 2 },
});
