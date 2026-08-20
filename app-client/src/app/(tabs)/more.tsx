import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Switch,
  TextInput,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import { loadServerConfig, saveServerConfig } from '../../utils/storage';
import { setBaseURL, setApiKey } from '../../api/client';

interface MenuItem {
  icon: string;
  label: string;
  subtitle: string;
  route: string;
}

const menuItems: MenuItem[] = [
  { icon: 'document-text', label: 'Summaries', subtitle: 'Daily & weekly summaries', route: '/(tabs)/summaries' },
  { icon: 'help-circle', label: 'FAQ', subtitle: 'Frequently asked questions', route: '/(tabs)/faq' },
  { icon: 'bookmark', label: 'Bookmarks', subtitle: 'Saved answers', route: '/(tabs)/bookmarks' },
  { icon: 'time', label: 'Chat History', subtitle: 'Past conversations', route: '/(tabs)/history' },
  { icon: 'school', label: 'Lesson Archive', subtitle: 'Past lessons', route: '/(tabs)/lessons-archive' },
];

export default function MoreScreen() {
  const router = useRouter();
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const [apiKeyValue, setApiKeyValue] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    loadServerConfig().then(({ url, apiKey }: { url: string; apiKey: string }) => {
      setServerUrl(url);
      setApiKeyValue(apiKey);
    });
  }, []);

  const handleNotificationToggle = async (value: boolean) => {
    if (value) {
      try {
        const { default: Notifications } = await import('expo-notifications');
        const { status } = await Notifications.requestPermissionsAsync();
        if (status !== 'granted') {
          Alert.alert('Permission Denied', 'Enable notifications in system settings.');
          return;
        }
      } catch {
        Alert.alert('Error', 'Push notifications are not available on this platform.');
        return;
      }
    }
    setNotificationsEnabled(value);
  };

  const handleSaveSettings = () => {
    const trimmedUrl = serverUrl.trim().replace(/\/+$/, '');
    saveServerConfig(trimmedUrl, apiKeyValue.trim()).then(() => {
      setBaseURL(trimmedUrl);
      setApiKey(apiKeyValue.trim());
      Alert.alert('Saved', 'Server settings updated. Restart the app to apply.');
    });
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.header}>More</Text>

      {menuItems.map((item: MenuItem, i: number) => (
        <TouchableOpacity
          key={i}
          style={styles.menuItem}
          onPress={() => router.push(item.route as any)}
        >
          <Ionicons name={item.icon as any} size={22} color={Colors.primary} />
          <View style={styles.menuText}>
            <Text style={styles.menuLabel}>{item.label}</Text>
            <Text style={styles.menuSubtitle}>{item.subtitle}</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
        </TouchableOpacity>
      ))}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Preferences</Text>

        <View style={styles.toggleRow}>
          <Ionicons name="notifications-outline" size={22} color={Colors.warning} />
          <View style={styles.menuText}>
            <Text style={styles.menuLabel}>Push Notifications</Text>
            <Text style={styles.menuSubtitle}>New promos & lesson alerts</Text>
          </View>
          <Switch
            value={notificationsEnabled}
            onValueChange={handleNotificationToggle}
            trackColor={{ false: Colors.border, true: Colors.primary + '66' }}
            thumbColor={notificationsEnabled ? Colors.primary : Colors.textMuted}
          />
        </View>
      </View>

      <View style={styles.section}>
        <TouchableOpacity
          style={styles.settingsHeader}
          onPress={() => setShowSettings(!showSettings)}
        >
          <Ionicons name="settings-outline" size={22} color={Colors.textSecondary} />
          <Text style={styles.sectionTitle}>Server Settings</Text>
          <Ionicons
            name={showSettings ? 'chevron-up' : 'chevron-down'}
            size={18}
            color={Colors.textMuted}
          />
        </TouchableOpacity>

        {showSettings && (
          <View style={styles.settingsForm}>
            <Text style={styles.fieldLabel}>Server URL</Text>
            <TextInput
              style={styles.textInput}
              value={serverUrl}
              onChangeText={setServerUrl}
              placeholder="http://localhost:8090"
              placeholderTextColor={Colors.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Text style={styles.fieldLabel}>API Key (optional)</Text>
            <TextInput
              style={styles.textInput}
              value={apiKeyValue}
              onChangeText={setApiKeyValue}
              placeholder="Leave empty for open access"
              placeholderTextColor={Colors.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
            />
            <TouchableOpacity style={styles.saveButton} onPress={handleSaveSettings}>
              <Text style={styles.saveButtonText}>Save</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      <Text style={styles.versionText}>BigTree Client v1.0.0</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  content: { padding: 16 },
  header: { color: Colors.text, fontSize: 22, fontWeight: '700', marginBottom: 16 },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 12,
  },
  menuText: { flex: 1 },
  menuLabel: { color: Colors.text, fontSize: 15, fontWeight: '600' },
  menuSubtitle: { color: Colors.textSecondary, fontSize: 12, marginTop: 2 },
  section: { marginTop: 20 },
  sectionTitle: { color: Colors.text, fontSize: 16, fontWeight: '700', marginBottom: 12, flex: 1 },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 12,
  },
  settingsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  settingsForm: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  fieldLabel: { color: Colors.textSecondary, fontSize: 12, fontWeight: '600', marginBottom: 6, marginTop: 8 },
  textInput: {
    backgroundColor: Colors.inputBg,
    borderRadius: 8,
    padding: 10,
    color: Colors.text,
    fontSize: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  saveButton: {
    backgroundColor: Colors.primary,
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
    marginTop: 12,
  },
  saveButtonText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  versionText: {
    color: Colors.textMuted,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 32,
    marginBottom: 16,
  },
});
