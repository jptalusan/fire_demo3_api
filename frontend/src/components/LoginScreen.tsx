import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Button } from './ui/button';
import { Alert, AlertDescription } from './ui/alert';
import { Flame, Shield, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { register as apiRegister } from '../services/auth';

export function LoginScreen() {
  const { login } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === 'register') {
        await apiRegister(username, password);
        setNotice('Account created. Logging you in…');
      }
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader className="space-y-2 text-center">
          <div className="flex items-center justify-center gap-2 text-orange-500">
            <Flame className="h-7 w-7" />
            <Shield className="h-7 w-7" />
          </div>
          <CardTitle className="text-2xl">Fire Department Simulator</CardTitle>
          <CardDescription>Sign in to run dispatch simulations</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-1 mb-4 rounded-md bg-muted p-1">
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null); setNotice(null); }}
              className={`rounded-sm py-1.5 text-sm font-medium transition-colors ${
                mode === 'login' ? 'bg-background shadow text-foreground' : 'text-muted-foreground'
              }`}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(null); setNotice(null); }}
              className={`rounded-sm py-1.5 text-sm font-medium transition-colors ${
                mode === 'register' ? 'bg-background shadow text-foreground' : 'text-muted-foreground'
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={submit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  minLength={3}
                  required
                />
                {mode === 'register' && (
                  <p className="text-xs text-muted-foreground">At least 3 characters.</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  minLength={6}
                  required
                />
                {mode === 'register' && (
                  <p className="text-xs text-muted-foreground">At least 6 characters.</p>
                )}
              </div>

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              {notice && (
                <Alert>
                  <AlertDescription>{notice}</AlertDescription>
                </Alert>
              )}

              <Button type="submit" className="w-full" disabled={busy}>
                {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {mode === 'login' ? 'Sign in' : 'Create account'}
              </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
