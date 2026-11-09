import { AppNav } from "@/components/app/app-nav";
import { DataStatus } from "@/components/app/data-status";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <AppNav />
      <DataStatus />
      <main className="px-6 py-6">{children}</main>
    </div>
  );
}
