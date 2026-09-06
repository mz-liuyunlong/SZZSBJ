import { useState } from 'react'
import AppErrorBoundary from './components/errors/AppErrorBoundary'
import AppRoutes from './router/routes'

function App() {
  const [mockLoggedIn, setMockLoggedIn] = useState(false)

  return (
    <AppErrorBoundary>
      <AppRoutes
        mockLoggedIn={mockLoggedIn}
        onLogin={() => setMockLoggedIn(true)}
        onLogout={() => setMockLoggedIn(false)}
      />
    </AppErrorBoundary>
  )
}

export default App
