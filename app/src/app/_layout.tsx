/**
 * Root layout — wraps the entire app with providers.
 */
import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Slot, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View, StyleSheet } from 'react-native';
import { getToken } from '../api/client';
import { wsManager } from '../api/ws';
import { colors } from '../theme/colors';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5000 },
  },
});

// Wire WS manager to query client
wsManager.setQueryClient(queryClient);

export default function RootLayout() {
  const segments = useSegments();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Check if already authenticated
    const token = getToken();
    setReady(true);
    if (!token && segments[0] !== 'login') {
      router.replace('/login');
    }
  }, [segments]);

  if (!ready) return null;

  return (
    <QueryClientProvider client={queryClient}>
      <View style={styles.container}>
        <StatusBar style="light" />
        <Slot />
      </View>
    </QueryClientProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
});
