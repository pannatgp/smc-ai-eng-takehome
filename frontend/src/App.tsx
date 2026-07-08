import './App.css'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { AuthPage } from './auth/AuthPage'
import { ChatPage } from './chat/ChatPage'

function AppShell() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <ChatPage /> : <AuthPage />
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  )
}

export default App
