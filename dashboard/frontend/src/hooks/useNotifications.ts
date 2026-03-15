import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Hook that requests notification permission and provides a `notify()` function.
 */
export function useNotifications() {
  const permissionRef = useRef<NotificationPermission>('default')

  useEffect(() => {
    if (!('Notification' in window)) return
    permissionRef.current = Notification.permission
    if (Notification.permission === 'default') {
      Notification.requestPermission().then(p => {
        permissionRef.current = p
      })
    }
  }, [])

  const notify = useCallback((title: string, body: string, tag?: string) => {
    if (!('Notification' in window)) return
    if (permissionRef.current !== 'granted') return

    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then(reg => {
        reg.showNotification(title, {
          body,
          tag: tag || 'altior-bot',
          icon: '/favicon.svg',
          badge: '/favicon.svg',
        } as NotificationOptions)
      }).catch(() => {
        new Notification(title, { body, tag: tag || 'altior-bot' })
      })
    } else {
      new Notification(title, { body, tag: tag || 'altior-bot' })
    }
  }, [])

  return { notify }
}


/**
 * Hook that listens to WebSocket trade events and fires notifications.
 */
export function useTradeNotifications(lastMessage: unknown) {
  const { notify } = useNotifications()
  const processedRef = useRef(new Set<string>())

  useEffect(() => {
    if (!lastMessage || typeof lastMessage !== 'object') return
    const msg = lastMessage as Record<string, unknown>

    if (msg.type === 'trade_opened') {
      const key = `open_${msg.pair}_${msg.price}`
      if (processedRef.current.has(key)) return
      processedRef.current.add(key)
      notify(
        `Trade ouvert: ${msg.pair}`,
        `${String(msg.direction).toUpperCase()} ${msg.size} @ $${msg.price}\nStrategie: ${msg.strategy || 'auto'}`,
        `trade_${key}`,
      )
    }

    if (msg.type === 'trade_closed') {
      const key = `close_${msg.pair}_${msg.profit}`
      if (processedRef.current.has(key)) return
      processedRef.current.add(key)
      const profit = Number(msg.profit || 0)
      const emoji = profit >= 0 ? '+' : ''
      notify(
        `Trade ferme: ${msg.pair}`,
        `P&L: ${emoji}$${profit.toFixed(2)}`,
        `trade_${key}`,
      )
    }

    if (processedRef.current.size > 200) {
      const entries = Array.from(processedRef.current)
      processedRef.current = new Set(entries.slice(-100))
    }
  }, [lastMessage, notify])
}


function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}


/**
 * Hook for Web Push subscription (works even when app is closed).
 */
export function usePushSubscription(token: string) {
  const [isSubscribed, setIsSubscribed] = useState(false)
  const [isSupported, setIsSupported] = useState(false)

  useEffect(() => {
    const supported = 'serviceWorker' in navigator && 'PushManager' in window
    setIsSupported(supported)
    if (!supported) return

    navigator.serviceWorker.ready.then(reg => {
      reg.pushManager.getSubscription().then(sub => {
        setIsSubscribed(!!sub)
      })
    })
  }, [])

  const subscribe = async () => {
    if (!isSupported) return

    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return

    // Get VAPID public key from backend
    const res = await fetch('/api/push/vapid-key', {
      headers: { Authorization: `Bearer ${token}` },
    })
    const { publicKey } = await res.json()
    if (!publicKey) return

    const vapidKey = urlBase64ToUint8Array(publicKey)
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKey as BufferSource,
    })

    const subJson = sub.toJSON()
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        endpoint: subJson.endpoint,
        keys: {
          p256dh: subJson.keys?.p256dh || '',
          auth: subJson.keys?.auth || '',
        },
      }),
    })

    setIsSubscribed(true)
  }

  const unsubscribe = async () => {
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    if (sub) {
      await fetch('/api/push/unsubscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ endpoint: sub.endpoint }),
      })
      await sub.unsubscribe()
      setIsSubscribed(false)
    }
  }

  const testPush = async () => {
    await fetch('/api/push/test', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
  }

  return { isSubscribed, isSupported, subscribe, unsubscribe, testPush }
}
