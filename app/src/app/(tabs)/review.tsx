/**
 * Review screen — approve, edit, or reject pending messages.
 */
import React, { useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput,
  Alert, ActivityIndicator, RefreshControl, Modal,
} from 'react-native';
import {
  usePendingReviews, useApproveReview, useEditReview, useRejectReview,
  type ReviewItem,
} from '../../api/review';
import { colors, confidenceColor } from '../../theme/colors';

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function ReviewScreen() {
  const { data, isLoading, refetch } = usePendingReviews();
  const approveMut = useApproveReview();
  const editMut = useEditReview();
  const rejectMut = useRejectReview();

  const [refreshing, setRefreshing] = useState(false);
  const [editItem, setEditItem] = useState<ReviewItem | null>(null);
  const [editText, setEditText] = useState('');

  const onRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };

  const handleApprove = (id: string) => {
    Alert.alert('Approve', 'Post this draft answer to Discord?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Approve', style: 'default',
        onPress: () => approveMut.mutate(id),
      },
    ]);
  };

  const handleReject = (id: string) => {
    Alert.alert('Reject', 'Reject this answer and store as negative sample?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Reject', style: 'destructive',
        onPress: () => rejectMut.mutate(id),
      },
    ]);
  };

  const handleEditSubmit = () => {
    if (!editItem || !editText.trim()) return;
    editMut.mutate({ itemId: editItem.id, answer: editText.trim() });
    setEditItem(null);
    setEditText('');
  };

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const items = data?.items ?? [];

  return (
    <>
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {items.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>&#10003;</Text>
            <Text style={styles.emptyText}>No pending reviews</Text>
            <Text style={styles.emptySubtext}>All caught up!</Text>
          </View>
        ) : (
          <Text style={styles.header}>{items.length} pending review(s)</Text>
        )}

        {items.map((item) => (
          <View key={item.id} style={styles.card}>
            {/* Meta */}
            <View style={styles.meta}>
              <Text style={styles.channel}>#{item.channel_name}</Text>
              <Text style={[styles.confBadge, { color: confidenceColor(item.confidence) }]}>
                {item.confidence}/10
              </Text>
              <Text style={styles.time}>{timeAgo(item.created_at)}</Text>
            </View>

            {/* Author */}
            <Text style={styles.author}>{item.author_name}</Text>

            {/* Question */}
            <Text style={styles.label}>Question</Text>
            <Text style={styles.questionText}>{item.question}</Text>

            {/* Draft answer */}
            <Text style={styles.label}>Draft Answer</Text>
            <Text style={styles.draftText}>{item.draft_answer}</Text>

            {/* Context */}
            {item.context_snippets.length > 0 && (
              <>
                <Text style={styles.label}>Context</Text>
                {item.context_snippets.map((s, i) => (
                  <Text key={i} style={styles.snippet} numberOfLines={2}>
                    {s.text || '(empty)'}
                  </Text>
                ))}
              </>
            )}

            {/* Action buttons */}
            <View style={styles.actions}>
              <TouchableOpacity
                style={[styles.btn, styles.btnApprove]}
                onPress={() => handleApprove(item.id)}
              >
                <Text style={styles.btnText}>Approve</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btn, styles.btnEdit]}
                onPress={() => { setEditItem(item); setEditText(item.draft_answer); }}
              >
                <Text style={styles.btnText}>Edit</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btn, styles.btnReject]}
                onPress={() => handleReject(item.id)}
              >
                <Text style={styles.btnText}>Reject</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </ScrollView>

      {/* Edit modal */}
      <Modal visible={!!editItem} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Edit Answer</Text>
            <Text style={styles.modalQuestion} numberOfLines={3}>
              Q: {editItem?.question}
            </Text>
            <TextInput
              style={styles.editInput}
              value={editText}
              onChangeText={setEditText}
              multiline
              placeholder="Edit your answer..."
              placeholderTextColor={colors.textMuted}
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancel} onPress={() => setEditItem(null)}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSubmit} onPress={handleEditSubmit}>
                <Text style={styles.btnText}>Submit</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 32 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
  header: { fontSize: 16, fontWeight: '600', color: colors.textPrimary, marginBottom: 12 },
  emptyContainer: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon: { fontSize: 48, color: colors.success, marginBottom: 12 },
  emptyText: { fontSize: 18, fontWeight: '600', color: colors.textPrimary },
  emptySubtext: { fontSize: 14, color: colors.textMuted, marginTop: 4 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  channel: { fontSize: 13, color: colors.primary, fontWeight: '500' },
  confBadge: { fontSize: 13, fontWeight: '700' },
  time: { fontSize: 12, color: colors.textMuted, marginLeft: 'auto' },
  author: { fontSize: 13, color: colors.textSecondary, marginBottom: 10 },
  label: { fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', marginTop: 10, marginBottom: 4 },
  questionText: { fontSize: 14, color: colors.textPrimary, lineHeight: 20 },
  draftText: { fontSize: 14, color: colors.textSecondary, lineHeight: 20 },
  snippet: { fontSize: 12, color: colors.textMuted, marginBottom: 2, fontStyle: 'italic' },
  actions: { flexDirection: 'row', gap: 8, marginTop: 14 },
  btn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  btnApprove: { backgroundColor: colors.success },
  btnEdit: { backgroundColor: colors.primary },
  btnReject: { backgroundColor: colors.danger },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', padding: 20 },
  modalContent: { backgroundColor: colors.surface, borderRadius: 16, padding: 24, maxHeight: '80%' },
  modalTitle: { fontSize: 18, fontWeight: '700', color: colors.textPrimary, marginBottom: 12 },
  modalQuestion: { fontSize: 13, color: colors.textSecondary, marginBottom: 12 },
  editInput: {
    backgroundColor: colors.background,
    borderRadius: 8,
    padding: 14,
    color: colors.textPrimary,
    fontSize: 14,
    minHeight: 120,
    textAlignVertical: 'top',
    borderWidth: 1,
    borderColor: colors.border,
  },
  modalActions: { flexDirection: 'row', gap: 12, marginTop: 16, justifyContent: 'flex-end' },
  modalCancel: { paddingVertical: 10, paddingHorizontal: 20 },
  modalCancelText: { color: colors.textSecondary, fontSize: 14, fontWeight: '500' },
  modalSubmit: { backgroundColor: colors.primary, paddingVertical: 10, paddingHorizontal: 24, borderRadius: 8 },
});
