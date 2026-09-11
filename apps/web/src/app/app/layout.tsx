import { AppNav } from "@/components/app/app-nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <AppNav />
      <main className="px-6 py-6">{children}</main>
    </div>
  );
}
