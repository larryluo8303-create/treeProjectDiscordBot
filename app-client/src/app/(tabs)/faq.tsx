import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { useFAQ } from '../../api/faq';

export default function FAQScreen() {
  const { data, isLoading, error } = useFAQ();
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

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
        <Text style={styles.errorText}>Failed to load FAQ</Text>
      </View>
    );
  }

  const items: Array<{ question: string; answer: string }> = data?.items || [];

  if (items.length === 0) {
    return (
      <View style={styles.center}>
        <Ionicons name="help-circle-outline" size={64} color={Colors.textMuted} />
        <Text style={styles.emptyText}>No FAQ available yet</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>Frequently Asked Questions</Text>
      <Text style={styles.subtitle}>{items.length} questions</Text>

      {items.map((item: { question: string; answer: string }, idx: number) => {
        const isExpanded = expandedIdx === idx;
        return (
          <TouchableOpacity
            key={idx}
            style={styles.card}
            onPress={() => setExpandedIdx(isExpanded ? null : idx)}
            activeOpacity={0.7}
          >
            <View style={styles.questionRow}>
              <Ionicons name="help-circle" size={20} color={Colors.primary} />
              <Text style={styles.questionText}>{item.question}</Text>
              <Ionicons
                name={isExpanded ? 'chevron-up' : 'chevron-down'}
                size={18}
                color={Colors.textMuted}
              />
            </View>
            {isExpanded && (
              <View style={styles.answerContainer}>
                <Text style={styles.answerText}>{item.answer}</Text>
              </View>
            )}
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: Colors.background },
  header: { color: Colors.text, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  subtitle: { color: Colors.textSecondary, fontSize: 13, marginBottom: 16 },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  questionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  questionText: { color: Colors.text, fontSize: 15, fontWeight: '600', flex: 1 },
  answerContainer: {
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  answerText: { color: Colors.textSecondary, fontSize: 14, lineHeight: 22 },
  errorText: { color: Colors.danger, fontSize: 16, marginTop: 12 },
  emptyText: { color: Colors.textMuted, fontSize: 16, marginTop: 12 },
});
