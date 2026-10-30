import { StoreProvider } from '@/store'
import { ToastProvider } from '@/ui/toast'
import { Shell } from '@/layout/shell'

export default function App() {
  return (
    <StoreProvider>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </StoreProvider>
  )
}
