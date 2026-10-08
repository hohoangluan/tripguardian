import { lazy, Suspense } from 'react'
import { usePath } from './router'
import { isPhone } from './user/landing/device'

// The landing's 3D chunk and data start downloading now, in parallel with the page's own code, not after it.
if (location.pathname === '/' && !isPhone()) {
  void import('./user/landing/scene')
  void import('./user/landing/points.json')
}

const AdminApp = lazy(() => import('./admin/AdminApp'))
const UserApp = lazy(() => import('./user/UserApp'))

export function App() {
  const path = usePath()
  if (path.startsWith('/admin')) {
    return (
      <Suspense fallback={<div className="admin-boot">Đang mở Admin</div>}>
        <AdminApp />
      </Suspense>
    )
  }
  return (
    <Suspense fallback={null}>
      <UserApp path={path} />
    </Suspense>
  )
}
