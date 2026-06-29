import { create } from 'zustand'

type AdminState = {
  activeTab: string
  setActiveTab: (tab: string) => void
  adminToken: string | null
  setAdminToken: (token: string | null) => void
}

export const useAdminStore = create<AdminState>((set) => ({
  activeTab: 'overview',
  setActiveTab: (tab) => set({ activeTab: tab }),
  adminToken: sessionStorage.getItem('rivex_admin_token'),
  setAdminToken: (token) => {
    if (token) {
      sessionStorage.setItem('rivex_admin_token', token)
    } else {
      sessionStorage.removeItem('rivex_admin_token')
    }
    set({ adminToken: token })
  }
}))
