import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  DollarSign,
  FileText,
  LayoutDashboard,
  Megaphone,
  MonitorPlay,
  Phone,
  PhoneIncoming,
  Radio,
  ScrollText,
  Settings,
  ShieldOff,
  Upload,
  UserCog,
  Users2,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  permission?: string;
};

export type NavSection = {
  label: string;
  items: NavItem[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    label: "Genel Bakış",
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Satış",
    items: [
      { href: "/leads", label: "Lead'ler", icon: Users2, permission: "leads:read" },
      { href: "/leads/import", label: "Lead İçe Aktar", icon: Upload, permission: "leads:import" },
      { href: "/campaigns", label: "Kampanyalar", icon: Megaphone, permission: "campaign:read" },
    ],
  },
  {
    label: "Aramalar",
    items: [
      { href: "/calls", label: "Arama Geçmişi", icon: Phone, permission: "leads:read" },
      { href: "/calls/live", label: "Canlı Aramalar", icon: Radio, permission: "leads:read" },
      { href: "/callbacks", label: "Geri Aramalar", icon: PhoneIncoming, permission: "leads:read" },
      { href: "/demo-requests", label: "Demo Talepleri", icon: MonitorPlay, permission: "leads:read" },
      { href: "/suppression", label: "Arama Engeli", icon: ShieldOff, permission: "leads:read" },
    ],
  },
  {
    label: "İçerik",
    items: [
      { href: "/knowledge-base", label: "Bilgi Bankası", icon: BookOpen, permission: "leads:read" },
      { href: "/prompts", label: "Prompt Versiyonları", icon: FileText, permission: "leads:read" },
    ],
  },
  {
    label: "Yönetim",
    items: [
      { href: "/pricing", label: "Fiyatlandırma", icon: DollarSign, permission: "settings:read" },
      { href: "/settings", label: "Ayarlar / Entegrasyonlar", icon: Settings, permission: "settings:read" },
      { href: "/audit-logs", label: "Audit Log", icon: ScrollText, permission: "audit:read" },
      { href: "/users", label: "Kullanıcılar", icon: UserCog, permission: "users:manage" },
    ],
  },
];
