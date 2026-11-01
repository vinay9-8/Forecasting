import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import {
  allocateFaculty,
  downloadFile,
  downloadReport,
  generateSections,
  generateSyntheticData,
  getDashboardSummary,
  getErrorMessage,
  getRecords,
  resolveException,
  runForecast,
  validateDataset,
} from './api';
import type {
  ActionNotice,
  DashboardSummary,
  DataRecord,
} from './types';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

type IconName =
  | 'grid-1x2'
  | 'diagram-3'
  | 'book'
  | 'people'
  | 'person-badge'
  | 'graph-up-arrow'
  | 'columns-gap'
  | 'person-check'
  | 'exclamation-triangle'
  | 'clipboard2-check'
  | 'file-earmark-bar-graph'
  | 'gear';

interface NavItem {
  label: string;
  path: string;
  icon: IconName;
}

const navigation: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: 'grid-1x2' },
  { label: 'Programs', path: '/programs', icon: 'diagram-3' },
  { label: 'Courses', path: '/courses', icon: 'book' },
  { label: 'Students', path: '/students', icon: 'people' },
  { label: 'Faculty', path: '/faculty', icon: 'person-badge' },
  { label: 'Demand Forecasting', path: '/forecasting', icon: 'graph-up-arrow' },
  { label: 'Section Allocation', path: '/sections', icon: 'columns-gap' },
  { label: 'Faculty Allocation', path: '/faculty-allocation', icon: 'person-check' },
  { label: 'Exceptions', path: '/exceptions', icon: 'exclamation-triangle' },
  { label: 'Data Validation', path: '/validation', icon: 'clipboard2-check' },
  { label: 'Reports', path: '/reports', icon: 'file-earmark-bar-graph' },
  { label: 'Settings', path: '/settings', icon: 'gear' },
];

const routeTitles: Record<string, string> = Object.fromEntries(
  navigation.map(({ path, label }) => [path, label]),
);

function Icon({ name, className = '' }: { name: string; className?: string }) {
  return <i className={`bi bi-${name} ${className}`} aria-hidden="true" />;
}

function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="programs" element={<RecordsPage title="Programs" endpoint="/programs" subtitle="Browse the academic programs in your institution." />} />
        <Route path="courses" element={<RecordsPage title="Courses" endpoint="/courses" subtitle="Course catalog and capacity details." />} />
        <Route path="students" element={<RecordsPage title="Students" endpoint="/students" subtitle="Student records and program affiliations." />} />
        <Route path="faculty" element={<RecordsPage title="Faculty" endpoint="/faculty" subtitle="Faculty directory and workload details." />} />
        <Route path="forecasting" element={<RecordsPage title="Demand Forecasting" endpoint="/forecast/results" subtitle="Review forecast results and run a new demand forecast." action="forecast" />} />
        <Route path="sections" element={<RecordsPage title="Section Allocation" endpoint="/allocations/sections" subtitle="Review generated course sections by term." action="sections" />} />
        <Route path="faculty-allocation" element={<RecordsPage title="Faculty Allocation" endpoint="/allocations/faculty" subtitle="Review teaching assignments and faculty workloads." action="faculty" />} />
        <Route path="exceptions" element={<RecordsPage title="Exceptions" endpoint="/exceptions" subtitle="Resolve items that need attention." exceptions />} />
        <Route path="validation" element={<RecordsPage title="Data Validation" endpoint="/validation/results" subtitle="Inspect dataset checks and run validation." action="validation" />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default App;

function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notice, setNotice] = useState<ActionNotice | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const location = useLocation();
  const pageTitle = routeTitles[location.pathname] || 'Dashboard';

  useEffect(() => {
    setSidebarOpen(false);
    setNotice(null);
  }, [location.pathname]);

  const perform = async (label: string, operation: () => Promise<unknown>) => {
    setBusyAction(label);
    setNotice(null);
    try {
      await operation();
      setNotice({ kind: 'success', message: `${label} completed successfully.` });
    } catch (error) {
      setNotice({ kind: 'error', message: getErrorMessage(error) });
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`} aria-label="Main navigation">
        <Link to="/" className="brand-lockup" aria-label="Northstar Academic Planning home">
          <span className="brand-mark"><Icon name="compass" /></span>
          <span>
            <strong>northstar</strong>
            <small>ACADEMIC PLANNING</small>
          </span>
        </Link>
        <div className="sidebar-label">WORKSPACE</div>
        <nav className="nav flex-column sidebar-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="help-mark"><Icon name="question-circle" /></div>
          <div><strong>Need a hand?</strong><span>Explore the workspace</span></div>
          <Icon name="arrow-up-right" className="help-arrow" />
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}>
            <Icon name="list" />
          </button>
          <div className="breadcrumb-line"><span>Workspace</span><Icon name="chevron-right" /><strong>{pageTitle}</strong></div>
          <div className="topbar-actions">
            <div className="api-indicator"><Icon name="plug" /> API configured</div>
          </div>
        </header>
        <div className="export-toolbar">
          <div className="toolbar-context"><span className="eyebrow">ACADEMIC OPERATIONS</span><span>Plan with clarity. Allocate with confidence.</span></div>
          <div className="toolbar-buttons">
            <button className="btn btn-quiet btn-sm" onClick={() => void perform('CSV export', () => downloadFile('/export/csv', 'academic-data.csv'))} disabled={busyAction !== null}>
              {busyAction === 'CSV export' ? <span className="spinner-border spinner-border-sm" /> : <Icon name="download" />} <span>Export CSV</span>
            </button>
            <button className="btn btn-quiet btn-sm" onClick={() => void perform('JSON export', () => downloadFile('/export/json', 'academic-data.json'))} disabled={busyAction !== null}>
              {busyAction === 'JSON export' ? <span className="spinner-border spinner-border-sm" /> : <Icon name="braces" />} <span>Export JSON</span>
            </button>
            <button className="btn btn-primary btn-sm report-button" onClick={() => void perform('Report download', downloadReport)} disabled={busyAction !== null}>
              {busyAction === 'Report download' ? <span className="spinner-border spinner-border-sm" /> : <Icon name="file-earmark-arrow-down" />} <span>Download report</span>
            </button>
          </div>
        </div>
        <section className="page-content">
          {notice && <ActionAlert notice={notice} onDismiss={() => setNotice(null)} />}
          <Outlet context={{ setNotice }} />
        </section>
        <footer className="page-footer"><span>Northstar Academic Planning</span><span>Make every seat count.</span></footer>
      </main>
    </div>
  );
}

function ActionAlert({ notice, onDismiss }: { notice: ActionNotice; onDismiss: () => void }) {
  return (
    <div className={`alert action-alert alert-${notice.kind === 'success' ? 'success' : 'danger'}`} role={notice.kind === 'error' ? 'alert' : 'status'} aria-live="polite">
      <Icon name={notice.kind === 'success' ? 'check-circle' : 'exclamation-circle'} />
      <span>{notice.message}</span>
      <button className="btn-close ms-auto" aria-label="Dismiss message" onClick={onDismiss} />
    </div>
  );
}

function PageHeading({ eyebrow, title, description, children }: { eyebrow?: string; title: string; description: string; children?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}

function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [mode, setMode] = useState<'starter' | 'full'>('starter');
  const [seed, setSeed] = useState('');
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<ActionNotice | null>(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSummary(await getDashboardSummary());
    } catch (requestError) {
      setError(getErrorMessage(requestError));
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadSummary(); }, [loadSummary, refresh]);

  const onGenerate = async (event: FormEvent) => {
    event.preventDefault();
    const parsedSeed = Number(seed);
    if (seed.trim() === '' || !Number.isSafeInteger(parsedSeed)) {
      setNotice({ kind: 'error', message: 'Enter a whole-number seed to generate synthetic data.' });
      return;
    }
    setGenerating(true);
    setNotice(null);
    try {
      await generateSyntheticData(mode, parsedSeed);
      setNotice({ kind: 'success', message: 'Synthetic data generated successfully.' });
      setRefresh((value) => value + 1);
    } catch (requestError) {
      setNotice({ kind: 'error', message: getErrorMessage(requestError) });
    } finally {
      setGenerating(false);
    }
  };

  return (
    <>
      <PageHeading eyebrow="OVERVIEW" title="Good planning starts here." description="A clear view of your academic landscape, all in one place.">
        <button className="btn btn-outline-primary" onClick={() => setRefresh((value) => value + 1)} disabled={loading}>
          <Icon name="arrow-clockwise" /> Refresh
        </button>
      </PageHeading>
      {notice && <ActionAlert notice={notice} onDismiss={() => setNotice(null)} />}
      <section className="surface-card synthetic-panel">
        <div className="synthetic-copy">
          <div className="synthetic-icon"><Icon name="database-add" /></div>
          <div>
            <h2>Get your workspace started</h2>
            <p>Generate synthetic data for a fresh planning workspace.</p>
          </div>
        </div>
        <form className="synthetic-form" onSubmit={(event) => void onGenerate(event)}>
          <label className="visually-hidden" htmlFor="synthetic-mode">Data generation mode</label>
          <select id="synthetic-mode" className="form-select" value={mode} onChange={(event) => setMode(event.target.value as 'starter' | 'full')}>
            <option value="starter">Starter dataset</option><option value="full">Full dataset</option>
          </select>
          <label className="visually-hidden" htmlFor="synthetic-seed">Random seed</label>
          <input id="synthetic-seed" className="form-control seed-input" type="number" step="1" value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="Seed" />
          <button className="btn btn-primary" type="submit" disabled={generating}>
            {generating ? <><span className="spinner-border spinner-border-sm" /> Generating…</> : <><Icon name="stars" /> Generate synthetic data</>}
          </button>
        </form>
      </section>

      {loading ? <LoadingState label="Loading dashboard summary…" /> : error ? <ErrorState message={error} onRetry={() => setRefresh((value) => value + 1)} /> : summary ? (
        <DashboardContent summary={summary} />
      ) : <EmptyState title="No dashboard summary available" description="The API returned no dashboard data." />}
    </>
  );
}

function DashboardContent({ summary }: { summary: DashboardSummary }) {
  const kpis = [
    { label: 'Programs', value: summary.programs, icon: 'diagram-3', tone: 'violet', foot: 'Academic pathways' },
    { label: 'Courses', value: summary.courses, icon: 'book', tone: 'blue', foot: 'In the course catalog' },
    { label: 'Students', value: summary.students, icon: 'people', tone: 'teal', foot: 'Across all programs' },
    { label: 'Faculty', value: summary.faculty, icon: 'person-badge', tone: 'amber', foot: 'Available instructors' },
    { label: 'Predicted enrollment', value: summary.predicted_enrollment, icon: 'graph-up-arrow', tone: 'cyan', foot: 'Forecasted students' },
    { label: 'Sections', value: summary.sections, icon: 'columns-gap', tone: 'indigo', foot: 'Planned for allocation' },
    { label: 'Unmet demand', value: summary.unmet_demand, icon: 'exclamation-triangle', tone: 'rose', foot: 'Seats below demand' },
    { label: 'Allocation success', value: `${summary.allocation_success_rate}%`, icon: 'check2-circle', tone: 'green', foot: 'Successful assignments' },
  ];

  return (
    <>
      <div className="section-title-row"><div><div className="eyebrow">AT A GLANCE</div><h2>Planning overview</h2></div><span className="data-source"><span className="status-dot" /> Live API data</span></div>
      <div className="kpi-grid">
        {kpis.map((kpi) => (
          <article className="surface-card kpi-card" key={kpi.label}>
            <div className={`kpi-icon ${kpi.tone}`}><Icon name={kpi.icon} /></div>
            <div className="kpi-label">{kpi.label}</div>
            <div className="kpi-value">{typeof kpi.value === 'number' ? kpi.value.toLocaleString() : kpi.value}</div>
            <div className="kpi-foot">{kpi.foot}</div>
          </article>
        ))}
      </div>
      <div className="charts-grid">
        <ChartCard title="Enrollment forecast" subtitle="Actual and predicted enrollment by term" className="chart-wide">
          <DataChart data={summary.forecast_history} empty="No forecast history is available.">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={summary.forecast_history} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="predictedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#10a9a0" stopOpacity={0.19} /><stop offset="95%" stopColor="#10a9a0" stopOpacity={0} /></linearGradient>
                  <linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#243f75" stopOpacity={0.14} /><stop offset="95%" stopColor="#243f75" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid stroke="#e9eef4" vertical={false} />
                <XAxis dataKey="term" tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend iconType="circle" iconSize={7} />
                <Area type="monotone" dataKey="actual" name="Actual" stroke="#243f75" strokeWidth={2.5} fill="url(#actualFill)" />
                <Area type="monotone" dataKey="predicted" name="Predicted" stroke="#10a9a0" strokeWidth={2.5} fill="url(#predictedFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </DataChart>
        </ChartCard>
        <ChartCard title="Demand distribution" subtitle="Enrollment demand by category">
          <DataChart data={summary.demand_distribution} empty="No demand distribution is available.">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={summary.demand_distribution} dataKey="count" nameKey="category" innerRadius={56} outerRadius={84} paddingAngle={3} stroke="none">
                  {summary.demand_distribution.map((entry, index) => <Cell key={entry.category} fill={chartPalette[index % chartPalette.length]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend iconType="circle" iconSize={7} />
              </PieChart>
            </ResponsiveContainer>
          </DataChart>
        </ChartCard>
        <ChartCard title="Faculty workload" subtitle="Assigned hours compared with capacity" className="chart-wide">
          <DataChart data={summary.faculty_workload} empty="No faculty workload data is available.">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.faculty_workload} margin={{ top: 8, right: 12, left: -12, bottom: 0 }} barGap={5}>
                <CartesianGrid stroke="#e9eef4" vertical={false} />
                <XAxis dataKey="faculty" tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} /><Legend iconType="circle" iconSize={7} />
                <Bar dataKey="assigned_hours" name="Assigned hours" fill="#10a9a0" radius={[4, 4, 0, 0]} />
                <Bar dataKey="max_hours" name="Maximum hours" fill="#dce6ef" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </DataChart>
        </ChartCard>
        <ChartCard title="Faculty status" subtitle="Faculty availability by status">
          <DataChart data={summary.faculty_status} empty="No faculty status data is available.">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.faculty_status} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#e9eef4" vertical={false} />
                <XAxis dataKey="status" tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" name="Faculty" fill="#4779c7" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </DataChart>
        </ChartCard>
        <ChartCard title="Capacity utilization" subtitle="Enrollment against course capacity" className="chart-wide">
          <DataChart data={summary.capacity_utilization} empty="No capacity utilization data is available.">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.capacity_utilization} margin={{ top: 8, right: 12, left: -12, bottom: 0 }} barGap={5}>
                <CartesianGrid stroke="#e9eef4" vertical={false} />
                <XAxis dataKey="course" tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} /><Legend iconType="circle" iconSize={7} />
                <Bar dataKey="enrollment" name="Enrollment" fill="#10a9a0" radius={[4, 4, 0, 0]} />
                <Bar dataKey="capacity" name="Capacity" fill="#dce6ef" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </DataChart>
        </ChartCard>
        <ChartCard title="Unmet demand by course" subtitle="Courses with demand beyond available seats">
          <DataChart data={summary.unmet_by_course} empty="No unmet demand by course is available.">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.unmet_by_course} layout="vertical" margin={{ top: 4, right: 12, left: 10, bottom: 0 }}>
                <CartesianGrid stroke="#e9eef4" horizontal={false} />
                <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 11 }} />
                <YAxis type="category" dataKey="course" width={76} tickLine={false} axisLine={false} tick={{ fill: '#8190a3', fontSize: 10 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="unmet" name="Unmet demand" fill="#e69a54" radius={[0, 5, 5, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </DataChart>
        </ChartCard>
      </div>
    </>
  );
}

const chartPalette = ['#10a9a0', '#4779c7', '#8d79d6', '#e6a14e', '#e16d7a', '#4b9d78'];
const tooltipStyle = { border: '1px solid #e5ebf2', borderRadius: '10px', boxShadow: '0 8px 24px rgba(27, 46, 75, .1)', fontSize: 12 };

function ChartCard({ title, subtitle, className = '', children }: { title: string; subtitle: string; className?: string; children: ReactNode }) {
  return <section className={`surface-card chart-card ${className}`}><div className="chart-heading"><div><h3>{title}</h3><p>{subtitle}</p></div></div><div className="chart-content">{children}</div></section>;
}

function DataChart({ data, empty, children }: { data: unknown[]; empty: string; children: ReactNode }) {
  return data.length === 0 ? <EmptyState title="Nothing to chart yet" description={empty} compact /> : <div className="chart-plot">{children}</div>;
}

function RecordsPage({
  title,
  endpoint,
  subtitle,
  action,
  exceptions = false,
}: {
  title: string;
  endpoint: string;
  subtitle: string;
  action?: 'forecast' | 'sections' | 'faculty' | 'validation';
  exceptions?: boolean;
}) {
  const [records, setRecords] = useState<DataRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState<ActionNotice | null>(null);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRecords(await getRecords(endpoint));
    } catch (requestError) {
      setError(getErrorMessage(requestError));
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => { void loadRecords(); }, [loadRecords, reload]);

  const handleResolve = async (record: DataRecord) => {
    const id = record.id;
    if (typeof id !== 'string' && typeof id !== 'number') {
      setNotice({ kind: 'error', message: 'This exception does not include an id and cannot be resolved.' });
      return;
    }
    try {
      await resolveException(id);
      setNotice({ kind: 'success', message: 'Exception resolved successfully.' });
      setReload((value) => value + 1);
    } catch (requestError) {
      setNotice({ kind: 'error', message: getErrorMessage(requestError) });
    }
  };

  return (
    <>
      <PageHeading eyebrow="WORKSPACE DATA" title={title} description={subtitle}>
        <button className="btn btn-outline-primary" onClick={() => setReload((value) => value + 1)} disabled={loading}><Icon name="arrow-clockwise" /> Refresh</button>
      </PageHeading>
      {notice && <ActionAlert notice={notice} onDismiss={() => setNotice(null)} />}
      {action && <WorkflowAction action={action} onSuccess={() => { setNotice({ kind: 'success', message: 'Operation completed successfully.' }); setReload((value) => value + 1); }} onError={(message) => setNotice({ kind: 'error', message })} />}
      {loading ? <LoadingState label={`Loading ${title.toLowerCase()}…`} /> : error ? <ErrorState message={error} onRetry={() => setReload((value) => value + 1)} /> : (
        <RecordsTable records={records} title={title} exceptions={exceptions} onResolve={(record) => void handleResolve(record)} />
      )}
    </>
  );
}

function WorkflowAction({ action, onSuccess, onError }: { action: 'forecast' | 'sections' | 'faculty' | 'validation'; onSuccess: () => void; onError: (message: string) => void }) {
  const [term, setTerm] = useState('');
  const [working, setWorking] = useState(false);
  const config = {
    forecast: { title: 'Run demand forecast', description: 'Generate a demand forecast for a planning term.', icon: 'graph-up-arrow' },
    sections: { title: 'Generate sections', description: 'Create section allocations for a planning term.', icon: 'columns-gap' },
    faculty: { title: 'Allocate faculty', description: 'Assign faculty to sections for a planning term.', icon: 'person-check' },
    validation: { title: 'Validate dataset', description: 'Run the dataset checks and refresh validation results.', icon: 'clipboard2-check' },
  }[action];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (action !== 'validation' && term.trim() === '') {
      onError('Enter a term code before continuing.');
      return;
    }
    setWorking(true);
    try {
      if (action === 'validation') await validateDataset();
      else if (action === 'forecast') await runForecast(term.trim());
      else if (action === 'sections') await generateSections(term.trim());
      else await allocateFaculty(term.trim());
      onSuccess();
    } catch (error) {
      onError(getErrorMessage(error));
    } finally {
      setWorking(false);
    }
  };

  return (
    <form className="surface-card workflow-card" onSubmit={(event) => void submit(event)}>
      <div className="workflow-intro"><span className="workflow-icon"><Icon name={config.icon} /></span><div><h2>{config.title}</h2><p>{config.description}</p></div></div>
      <div className="workflow-controls">
        {action !== 'validation' && <><label className="visually-hidden" htmlFor={`${action}-term`}>Term code</label><input id={`${action}-term`} className="form-control term-input" value={term} onChange={(event) => setTerm(event.target.value)} placeholder="Enter term code" required /></>}
        <button className="btn btn-primary" type="submit" disabled={working}>{working ? <><span className="spinner-border spinner-border-sm" /> Working…</> : <><Icon name={config.icon} /> {config.title}</>}</button>
      </div>
    </form>
  );
}

function RecordsTable({ records, title, exceptions, onResolve }: { records: DataRecord[]; title: string; exceptions: boolean; onResolve: (record: DataRecord) => void }) {
  const [query, setQuery] = useState('');
  const [filterKey, setFilterKey] = useState('');
  const [filterValue, setFilterValue] = useState('');

  const keys = useMemo(() => {
    const found = new Set<string>();
    records.slice(0, 100).forEach((record) => Object.keys(record).forEach((key) => found.add(key)));
    return [...found];
  }, [records]);
  const filterValues = useMemo(() => {
    if (!filterKey) return [];
    return [...new Set(records.map((record) => displayValue(record[filterKey])).filter((value) => value !== '—'))].sort();
  }, [records, filterKey]);
  const filtered = records.filter((record) => {
    const searchable = Object.values(record).map(displayValue).join(' ').toLowerCase();
    const matchesText = searchable.includes(query.trim().toLowerCase());
    const matchesField = !filterKey || !filterValue || displayValue(record[filterKey]) === filterValue;
    return matchesText && matchesField;
  });
  const columns = keys.slice(0, 7);

  return (
    <section className="surface-card table-card">
      <div className="table-heading">
        <div><h2>{title} records</h2><p>{records.length.toLocaleString()} {records.length === 1 ? 'record' : 'records'} from the API</p></div>
        <div className="table-controls">
          <div className="search-control"><Icon name="search" /><label className="visually-hidden" htmlFor="record-search">Search records</label><input id="record-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search records…" /></div>
          <div className="filter-controls">
            <label className="visually-hidden" htmlFor="filter-field">Filter field</label>
            <select id="filter-field" value={filterKey} onChange={(event) => { setFilterKey(event.target.value); setFilterValue(''); }} aria-label="Filter by field">
              <option value="">All fields</option>{keys.map((key) => <option key={key} value={key}>{humanize(key)}</option>)}
            </select>
            <label className="visually-hidden" htmlFor="filter-value">Filter value</label>
            <select id="filter-value" value={filterValue} onChange={(event) => setFilterValue(event.target.value)} disabled={!filterKey} aria-label="Select filter value">
              <option value="">All values</option>{filterValues.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>
        </div>
      </div>
      {records.length === 0 ? <EmptyState title="No records yet" description={`The API returned no ${title.toLowerCase()} records.`} /> : filtered.length === 0 ? (
        <EmptyState title="No matching records" description="Try adjusting your search or filters." />
      ) : (
        <div className="table-responsive">
          <table className="table align-middle data-table">
            <thead><tr>{columns.map((key) => <th key={key} scope="col">{humanize(key)}</th>)}{exceptions && <th scope="col">Action</th>}</tr></thead>
            <tbody>{filtered.map((record, rowIndex) => (
              <tr key={typeof record.id === 'string' || typeof record.id === 'number' ? record.id : rowIndex}>
                {columns.map((key) => <td key={key} title={displayValue(record[key])}><span className={key.toLowerCase().includes('status') ? `status-pill ${statusTone(record[key])}` : ''}>{displayValue(record[key])}</span></td>)}
                {exceptions && <td><button className="btn btn-sm btn-outline-primary" disabled={String(record.status || '').toLowerCase() === 'resolved'} onClick={() => onResolve(record)}>{String(record.status || '').toLowerCase() === 'resolved' ? 'Resolved' : 'Resolve'}</button></td>}
              </tr>
            ))}</tbody>
          </table>
          <div className="table-footnote">Showing {filtered.length.toLocaleString()} of {records.length.toLocaleString()} records</div>
        </div>
      )}
    </section>
  );
}

function ReportsPage() {
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<ActionNotice | null>(null);
  const [records, setRecords] = useState<DataRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getRecords('/forecast/results').then((data) => {
      if (active) setRecords(data);
    }).catch((requestError: unknown) => {
      if (active) setError(getErrorMessage(requestError));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [reload]);

  const generate = async () => {
    setWorking(true);
    setNotice(null);
    try {
      await downloadReport();
      setNotice({ kind: 'success', message: 'Report downloaded successfully.' });
    } catch (requestError) {
      setNotice({ kind: 'error', message: getErrorMessage(requestError) });
    } finally {
      setWorking(false);
    }
  };

  return (
    <>
      <PageHeading eyebrow="INSIGHTS & EXPORTS" title="Reports" description="Download a report for your planning team or review forecast results." />
      {notice && <ActionAlert notice={notice} onDismiss={() => setNotice(null)} />}
      <section className="surface-card report-hero">
        <div className="report-art"><Icon name="file-earmark-bar-graph" /></div>
        <div className="report-copy"><div className="eyebrow">ACADEMIC SUMMARY</div><h2>Planning report</h2><p>Download the latest report from your academic planning API. The response may be provided as CSV or JSON.</p></div>
        <button className="btn btn-primary" onClick={() => void generate()} disabled={working}>{working ? <><span className="spinner-border spinner-border-sm" /> Preparing…</> : <><Icon name="download" /> Download report</>}</button>
      </section>
      <div className="section-title-row report-section-title"><div><div className="eyebrow">LATEST RESULTS</div><h2>Forecast results</h2></div><Link className="text-link" to="/forecasting">Open forecasting <Icon name="arrow-right" /></Link></div>
      {loading ? <LoadingState label="Loading forecast results…" /> : error ? <ErrorState message={error} onRetry={() => setReload((value) => value + 1)} /> : <RecordsTable records={records} title="Forecast results" exceptions={false} onResolve={() => undefined} />}
    </>
  );
}

function SettingsPage() {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
  return (
    <>
      <PageHeading eyebrow="WORKSPACE PREFERENCES" title="Settings" description="Review the dashboard connection and workspace configuration." />
      <section className="surface-card settings-card">
        <div className="settings-section-icon"><Icon name="plug" /></div>
        <div className="settings-body">
          <h2>API connection</h2><p>The dashboard requests live data from the configured API base URL.</p>
          <label htmlFor="api-base-url">API base URL</label>
          <div className="input-group settings-url"><span className="input-group-text"><Icon name="link-45deg" /></span><input id="api-base-url" className="form-control" value={baseUrl} readOnly /><span className="input-group-text setting-readonly">Environment</span></div>
          <div className="settings-hint"><Icon name="info-circle" /> Configure <code>VITE_API_BASE_URL</code> in your frontend environment before starting the app.</div>
        </div>
      </section>
      <section className="surface-card settings-info"><div className="settings-section-icon soft-teal"><Icon name="shield-check" /></div><div><h2>Data handling</h2><p>Records and metrics are requested from the API. No sample data is stored or displayed by the dashboard.</p></div></section>
    </>
  );
}

function NotFoundPage() {
  return <div className="not-found"><span className="not-found-icon"><Icon name="compass" /></span><h1>Page not found</h1><p>This destination isn’t part of the workspace.</p><Link className="btn btn-primary" to="/">Back to dashboard</Link></div>;
}

function LoadingState({ label }: { label: string }) {
  return <div className="surface-card state-card" role="status" aria-live="polite"><span className="spinner-border spinner-border-sm" aria-hidden="true" /><span>{label}</span></div>;
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="surface-card state-card error-state" role="alert"><span className="state-icon"><Icon name="exclamation-triangle" /></span><div><h2>We couldn’t load this data</h2><p>{message}</p><button className="btn btn-outline-primary btn-sm" onClick={onRetry}><Icon name="arrow-clockwise" /> Try again</button></div></div>;
}

function EmptyState({ title, description, compact = false }: { title: string; description: string; compact?: boolean }) {
  return <div className={`empty-state ${compact ? 'empty-compact' : ''}`}><span className="empty-icon"><Icon name="inbox" /></span><strong>{title}</strong><span>{description}</span></div>;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function humanize(value: string): string {
  return value.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusTone(value: unknown): string {
  const normalized = String(value).toLowerCase();
  if (normalized.includes('resolved') || normalized.includes('active') || normalized.includes('available') || normalized.includes('passed')) return 'status-positive';
  if (normalized.includes('open') || normalized.includes('pending') || normalized.includes('warning')) return 'status-warning';
  if (normalized.includes('failed') || normalized.includes('error')) return 'status-negative';
  return 'status-neutral';
}
