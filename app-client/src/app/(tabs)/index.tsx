import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { Colors, confidenceColor } from '../../theme/colors';
import { useSendMessage, type ChatMessage } from '../../api/chat';
import { useAnalyzeImage } from '../../api/vision';
import {
  saveCurrentSession,
  saveBookmark,
  type ChatSession,
} from '../../utils/storage';

export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sessionId] = useState(() => Date.now().toString(36));
  const flatListRef = useRef<FlatList>(null);
  const sendMutation = useSendMessage();
  const visionMutation = useAnalyzeImage();
  const isBusy = sendMutation.isPending || visionMutation.isPending;

  // Persist session on message change
  useEffect(() => {
    if (messages.length === 0) return;
    const firstUserMsg = messages.find((m: ChatMessage) => m.role === 'user');
    const session: ChatSession = {
      id: sessionId,
      title: firstUserMsg?.content.slice(0, 40) || 'New Chat',
      messages,
      createdAt: messages[0]?.timestamp || Date.now(),
      updatedAt: Date.now(),
    };
    saveCurrentSession(session).catch(() => {});
  }, [messages, sessionId]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || isBusy) return;

    const userMsg: ChatMessage = {
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev: ChatMessage[]) => [...prev, userMsg]);
    setInput('');

    const history = messages
      .filter((m: ChatMessage) => m.role === 'user' || m.role === 'assistant')
      .slice(-10)
      .map((m: ChatMessage) => ({ role: m.role, content: m.content }));

    sendMutation.mutate(
      { message: text, conversation_history: history },
      {
        onSuccess: (data) => {
          const botMsg: ChatMessage = {
            role: 'assistant',
            content: data.answer,
            confidence: data.confidence,
            sources: data.sources,
            timestamp: Date.now(),
          };
          setMessages((prev: ChatMessage[]) => [...prev, botMsg]);
        },
        onError: () => {
          const errMsg: ChatMessage = {
            role: 'assistant',
            content: '抱歉，无法连接到服务器，请稍后重试。',
            timestamp: Date.now(),
          };
          setMessages((prev: ChatMessage[]) => [...prev, errMsg]);
        },
      },
    );
  }, [input, messages, isBusy, sendMutation]);

  const handlePickImage = useCallback(async () => {
    if (isBusy) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
      allowsEditing: false,
    });
    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const userMsg: ChatMessage = {
      role: 'user',
      content: input.trim() || '📸 Chart uploaded for analysis',
      imageUri: asset.uri,
      timestamp: Date.now(),
    };
    setMessages((prev: ChatMessage[]) => [...prev, userMsg]);
    const captionText = input.trim();
    setInput('');

    visionMutation.mutate(
      { imageUri: asset.uri, text: captionText },
      {
        onSuccess: (data) => {
          const botMsg: ChatMessage = {
            role: 'assistant',
            content: data.answer,
            confidence: data.confidence,
            timestamp: Date.now(),
          };
          setMessages((prev: ChatMessage[]) => [...prev, botMsg]);
        },
        onError: () => {
          const errMsg: ChatMessage = {
            role: 'assistant',
            content: '抱歉，图片分析失败，请稍后重试。',
            timestamp: Date.now(),
          };
          setMessages((prev: ChatMessage[]) => [...prev, errMsg]);
        },
      },
    );
  }, [input, isBusy, visionMutation]);

  const handleBookmark = useCallback((item: ChatMessage) => {
    const prevUser = [...messages].reverse().find(
      (m: ChatMessage) => m.role === 'user' && m.timestamp < item.timestamp
    );
    saveBookmark({
      id: Date.now().toString(36),
      question: prevUser?.content || '(image analysis)',
      answer: item.content,
      confidence: item.confidence || 0,
      savedAt: Date.now(),
    }).then(() => {
      Alert.alert('Saved', 'Answer bookmarked!');
    }).catch(() => {});
  }, [messages]);

  const renderMessage = ({ item }: { item: ChatMessage }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.botBubble]}>
        {!isUser && (
          <View style={styles.botHeader}>
            <Ionicons name="leaf" size={14} color={Colors.success} />
            <Text style={styles.botName}>BigTree</Text>
            {item.confidence !== undefined && (
              <View style={[styles.confidenceBadge, { backgroundColor: confidenceColor(item.confidence) + '22' }]}>
                <Text style={[styles.confidenceText, { color: confidenceColor(item.confidence) }]}>
                  {item.confidence}/10
                </Text>
              </View>
            )}
            <TouchableOpacity onPress={() => handleBookmark(item)} style={styles.bookmarkBtn}>
              <Ionicons name="bookmark-outline" size={14} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        )}
        {isUser && item.imageUri && (
          <Image source={{ uri: item.imageUri }} style={styles.chatImage} resizeMode="cover" />
        )}
        <Text style={[styles.messageText, isUser && styles.userText]}>{item.content}</Text>
        <Text style={styles.timeText}>
          {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </Text>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {messages.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="chatbubbles-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.emptyTitle}>BigTree Chat</Text>
          <Text style={styles.emptySubtitle}>Ask questions or upload charts for analysis</Text>
          <View style={styles.suggestionsContainer}>
            {['ES今天怎么看？', '什么是中枢？', '如何判断趋势？'].map((s: string, i: number) => (
              <TouchableOpacity
                key={i}
                style={styles.suggestion}
                onPress={() => { setInput(s); }}
              >
                <Text style={styles.suggestionText}>{s}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity style={[styles.suggestion, { borderColor: Colors.warning }]} onPress={handlePickImage}>
              <Text style={[styles.suggestionText, { color: Colors.warning }]}>📸 Upload a chart</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderMessage}
          keyExtractor={(_: ChatMessage, i: number) => String(i)}
          contentContainerStyle={styles.messageList}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
        />
      )}

      {isBusy && (
        <View style={styles.typingIndicator}>
          <ActivityIndicator size="small" color={Colors.primary} />
          <Text style={styles.typingText}>
            {visionMutation.isPending ? 'Analyzing chart...' : 'BigTree is thinking...'}
          </Text>
        </View>
      )}

      <View style={styles.inputBar}>
        <TouchableOpacity style={styles.imageButton} onPress={handlePickImage} disabled={isBusy}>
          <Ionicons name="camera" size={22} color={isBusy ? Colors.textMuted : Colors.primary} />
        </TouchableOpacity>
        <TextInput
          style={styles.input}
          placeholder="Ask a question..."
          placeholderTextColor={Colors.textMuted}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={handleSend}
          returnKeyType="send"
          multiline
          maxLength={2000}
        />
        <TouchableOpacity
          style={[styles.sendButton, (!input.trim() || isBusy) && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!input.trim() || isBusy}
        >
          <Ionicons name="send" size={20} color="#fff" />
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  messageList: { padding: 16, paddingBottom: 8 },
  bubble: {
    maxWidth: '85%',
    padding: 12,
    borderRadius: 16,
    marginBottom: 8,
  },
  userBubble: {
    backgroundColor: Colors.userBubble,
    alignSelf: 'flex-end',
    borderBottomRightRadius: 4,
  },
  botBubble: {
    backgroundColor: Colors.botBubble,
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  botHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
    gap: 6,
  },
  botName: { color: Colors.success, fontSize: 12, fontWeight: '600' },
  confidenceBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
  },
  confidenceText: { fontSize: 10, fontWeight: '700' },
  messageText: { color: Colors.text, fontSize: 15, lineHeight: 22 },
  userText: { color: '#fff' },
  timeText: {
    color: Colors.textMuted,
    fontSize: 10,
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  sourcesContainer: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  sourcesLabel: { color: Colors.textSecondary, fontSize: 11, fontWeight: '600', marginBottom: 4 },
  sourceItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginBottom: 4,
  },
  sourceType: {
    color: Colors.info,
    fontSize: 10,
    fontWeight: '600',
    backgroundColor: Colors.info + '22',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
    overflow: 'hidden',
  },
  sourceText: { color: Colors.textSecondary, fontSize: 11, flex: 1 },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  emptyTitle: {
    color: Colors.text,
    fontSize: 24,
    fontWeight: '700',
    marginTop: 16,
  },
  emptySubtitle: {
    color: Colors.textSecondary,
    fontSize: 14,
    marginTop: 8,
    textAlign: 'center',
  },
  suggestionsContainer: {
    marginTop: 24,
    gap: 8,
    width: '100%',
    maxWidth: 300,
  },
  suggestion: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 20,
    alignItems: 'center',
  },
  suggestionText: { color: Colors.primary, fontSize: 14 },
  typingIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 8,
  },
  typingText: { color: Colors.textSecondary, fontSize: 13 },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: 12,
    paddingBottom: Platform.OS === 'ios' ? 28 : 12,
    backgroundColor: Colors.surface,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    gap: 8,
  },
  input: {
    flex: 1,
    backgroundColor: Colors.inputBg,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    color: Colors.text,
    fontSize: 15,
    maxHeight: 100,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  sendButton: {
    backgroundColor: Colors.primary,
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: { opacity: 0.4 },
  imageButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  chatImage: {
    width: '100%',
    height: 180,
    borderRadius: 10,
    marginBottom: 8,
  },
  bookmarkBtn: {
    marginLeft: 'auto',
    padding: 4,
  },
});
