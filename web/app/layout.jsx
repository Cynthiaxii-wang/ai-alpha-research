import '../src/styles.css'

export const metadata = {
  title: 'AI Alpha Research',
  description: 'AI 价值链、市场信号与需求兑现链研究平台',
  icons: { icon: '/favicon.svg' },
}

export const viewport = { themeColor: '#07111f' }

export default function RootLayout({ children }) {
  return <html lang="zh-CN"><body>{children}</body></html>
}
