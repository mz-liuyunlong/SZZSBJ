import { useState } from 'react'
import AppErrorBoundary from '@/components/errors/AppErrorBoundary'
import AppFeedbackProvider from '@/shared/feedback/AppFeedbackProvider'
import type { MockAuthUser } from '@/mocks/auth'
import AppRoutes from '@/router/routes'
import '@/styles/globalOverlay.css'
import '@/styles/globalShellPolish.css'
import '@/styles/developedPagesOrderProfitSkin.css'

function App() {
  const [mockUser, setMockUser] = useState<MockAuthUser>()

  return (
    <AppErrorBoundary>
      <AppFeedbackProvider>
        <AppRoutes
          mockLoggedIn={Boolean(mockUser)}
          currentUser={mockUser}
          onLogin={setMockUser}
          onLogout={() => setMockUser(undefined)}
        />
      </AppFeedbackProvider>
    </AppErrorBoundary>
  )
}

export default App
