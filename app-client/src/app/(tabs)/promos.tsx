import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Linking,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { usePromos, useLessons } from '../../api/promos';

export default function PromosScreen() {
  const promos = usePromos();
  const lessons = useLessons();
  const isLoading = promos.isLoading || lessons.isLoading;

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  const promoItems: Array<{ title: string; description: string; scheduled_at: string; url?: string }> =
    promos.data?.items || [];
  const lessonItems: Array<{ title: string; content: string; scheduled_at: string; repeat?: string }> =
    lessons.data?.items || [];
  const hasContent = promoItems.length > 0 || lessonItems.length > 0;

  if (!hasContent) {
    return (
      <View style={styles.center}>
        <Ionicons name="calendar-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.emptyTitle}>No Upcoming Events</Text>
        <Text style={styles.emptySubtitle}>Check back later for promotions and lessons</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {promoItems.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <Ionicons name="megaphone" size={20} color={Colors.warning} />
            <Text style={styles.sectionTitle}>Promotions</Text>
          </View>
          {promoItems.map((p: { title: string; description: string; scheduled_at: string; url?: string }, i: number) => (
            <View key={`p-${i}`} style={styles.card}>
              <Text style={styles.cardTitle}>{p.title}</Text>
              <Text style={styles.cardDesc}>{p.description}</Text>
              <View style={styles.cardFooter}>
                <Ionicons name="time-outline" size={14} color={Colors.textMuted} />
                <Text style={styles.cardTime}>
                  {new Date(p.scheduled_at).toLocaleDateString()} {new Date(p.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Text>
              </View>
              {p.url ? (
                <TouchableOpacity
                  style={styles.linkButton}
                  onPress={() => Linking.openURL(p.url!)}
                >
                  <Text style={styles.linkText}>Learn More</Text>
                  <Ionicons name="open-outline" size={14} color={Colors.primary} />
                </TouchableOpacity>
              ) : null}
            </View>
          ))}
        </>
      )}

      {lessonItems.length > 0 && (
        <>
          <View style={[styles.sectionHeader, promoItems.length > 0 && { marginTop: 24 }]}>
            <Ionicons name="school" size={20} color={Colors.info} />
            <Text style={styles.sectionTitle}>Lessons</Text>
          </View>
          {lessonItems.map((ls: { title: string; content: string; scheduled_at: string; repeat?: string }, i: number) => (
            <View key={`l-${i}`} style={styles.card}>
              <Text style={styles.cardTitle}>{ls.title}</Text>
              <Text style={styles.cardDesc}>{ls.content}</Text>
              <View style={styles.cardFooter}>
                <Ionicons name="time-outline" size={14} color={Colors.textMuted} />
                <Text style={styles.cardTime}>
                  {new Date(ls.scheduled_at).toLocaleDateString()} {new Date(ls.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </Text>
                {ls.repeat && ls.repeat !== 'none' && (
                  <View style={styles.repeatBadge}>
                    <Ionicons name="repeat" size={12} color={Colors.accent} />
                    <Text style={styles.repeatText}>{ls.repeat}</Text>
                  </View>
                )}
              </View>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  emptyTitle: { color: Colors.text, fontSize: 20, fontWeight: '700', marginTop: 16 },
  emptySubtitle: { color: Colors.textSecondary, fontSize: 14, marginTop: 8 },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  sectionTitle: { color: Colors.text, fontSize: 18, fontWeight: '700' },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardTitle: { color: Colors.text, fontSize: 16, fontWeight: '600', marginBottom: 6 },
  cardDesc: { color: Colors.textSecondary, fontSize: 14, lineHeight: 20, marginBottom: 8 },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  cardTime: { color: Colors.textMuted, fontSize: 12 },
  repeatBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginLeft: 8,
    backgroundColor: Colors.accent + '22',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  repeatText: { color: Colors.accent, fontSize: 11, fontWeight: '600' },
  linkButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 8,
    alignSelf: 'flex-start',
  },
  linkText: { color: Colors.primary, fontSize: 13, fontWeight: '600' },
});
