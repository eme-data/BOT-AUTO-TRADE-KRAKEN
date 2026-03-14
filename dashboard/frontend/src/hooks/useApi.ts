import axios from 'axios'

export function useApi(token: string) {
  const api = axios.create({
    baseURL: '/api',
    headers: { Authorization: `Bearer ${token}` },
  })

  return api
}
