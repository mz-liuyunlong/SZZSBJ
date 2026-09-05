import { useState } from 'react'
import AppRoutes from './router/routes'

function App() {
  const [mockLoggedIn, setMockLoggedIn] = useState(false)

  return (
    <AppRoutes
      mockLoggedIn={mockLoggedIn}
      onLogin={() => setMockLoggedIn(true)}
      onLogout={() => setMockLoggedIn(false)}
    />
  )
}

export default App
