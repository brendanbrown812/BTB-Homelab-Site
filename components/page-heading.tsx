export function PageHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return <div className="mb-8"><p className="mb-2 text-xs font-semibold uppercase tracking-[.18em] text-primary">{eyebrow}</p><h1 className="text-3xl font-black tracking-[-.035em] sm:text-4xl">{title}</h1><p className="mt-2 max-w-2xl text-base leading-relaxed text-slate-400">{children}</p></div>;
}
