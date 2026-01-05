import pandas as pd
import json
import datetime
import unicodedata

def normalize_name(name):
    if pd.isna(name): return "Desconocido"
    # Normalize unicode characters
    name = unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('ASCII')
    return name.strip().title()

def parse_custom_time(time_str):
    if pd.isna(time_str): return None
    # Normalize unicode to handle \u202f (narrow no-break space) and other weirdness
    time_str = str(time_str).strip()
    # Explicitly replace the narrow no-break space often found in Excel dates
    time_str = time_str.replace('\u202f', ' ').replace('\xa0', ' ')
    time_str = time_str.lower().replace('.', '')
    try:
        # Intenta parsear con formato 12 horas español custom
        # p. m. -> pm, a. m. -> am to simplify
        # Handle variations like "10:00 p m", "10:00 pm", "10:00 a. m."
        time_str = time_str.replace(' a m', ' am').replace(' p m', ' pm')
        
        return datetime.datetime.strptime(time_str, '%I:%M:%S %p').time()
    except ValueError:
        return None

def generate_dashboard():
    try:
        df = pd.read_excel('visitas angel.xlsx')
        
        # Data Cleaning
        df['Medico'] = df['Medico'].apply(normalize_name)
        df['Fecha de visita'] = pd.to_datetime(df['Fecha de visita'], errors='coerce')
        
        # Filter dates (remove NaT and unlikely dates, keep 2024+)
        df = df.dropna(subset=['Fecha de visita'])
        df = df[df['Fecha de visita'].dt.year >= 2024]
        
        df['Month'] = df['Fecha de visita'].dt.strftime('%Y-%m')
        
        # Parse Times & Calculate Duration
        if 'Ingreso' in df.columns and 'Salida' in df.columns:
            # Parse times combining with a dummy date to allow subtraction
            dummy_date = datetime.date(2000, 1, 1)
            
            def calculate_duration(row):
                t1 = parse_custom_time(row['Ingreso'])
                t2 = parse_custom_time(row['Salida'])
                if t1 and t2:
                    dt1 = datetime.datetime.combine(dummy_date, t1)
                    dt2 = datetime.datetime.combine(dummy_date, t2)
                    if dt2 < dt1: dt2 += datetime.timedelta(days=1) # Handle potential midnight crossing
                    return (dt2 - dt1).total_seconds() / 60
                return None

            df['Duration'] = df.apply(calculate_duration, axis=1)
            avg_duration_mins = round(df['Duration'].mean(), 1) if not df['Duration'].isna().all() else 0
        else:
            avg_duration_mins = 0

        # Metrics
        total_visits = len(df)
        unique_doctors = df['Medico'].nunique()
        
        # Daily Average
        unique_days = df['Fecha de visita'].dt.date.nunique()
        avg_visits_per_day = round(total_visits / unique_days, 1) if unique_days > 0 else 0
        
        # Handle Photos: Ensure they are strings and strip whitespace
        if 'Foto' in df.columns:
            df['Foto'] = df['Foto'].fillna('').astype(str).str.strip()
        else:
            df['Foto'] = ''
        
        # Visits per Month
        monthly_stats = df.groupby('Month').size().reset_index(name='count')
        monthly_stats = monthly_stats.sort_values('Month') # Ensure chronological order
        monthly_labels = monthly_stats['Month'].tolist()
        monthly_data = monthly_stats['count'].tolist()
        
        # Doctor Stats
        doctor_stats = []
        for medico, group in df.groupby('Medico'):
            visits = len(group)
            
            # Count by status
            visited_count = len(group[group['Estatus'].str.lower() == 'visitado']) if 'Estatus' in df.columns else 0
            not_visited_count = len(group[group['Estatus'].str.lower() == 'no visitado']) if 'Estatus' in df.columns else 0

            last_visit = group['Fecha de visita'].max().strftime('%Y-%m-%d')
            # Include 'Foto' in the selected columns
            comments = group[['Fecha de visita', 'Comentario', 'Estatus', 'Foto']].sort_values('Fecha de visita', ascending=False)
            comments['Fecha de visita'] = comments['Fecha de visita'].dt.strftime('%Y-%m-%d')
            comments_list = comments.to_dict('records')
            
            doctor_stats.append({
                'name': medico,
                'visits': visits,
                'visited_count': visited_count,
                'not_visited_count': not_visited_count,
                'last_visit': last_visit,
                'history': comments_list
            })
            
        doctor_stats.sort(key=lambda x: x['visits'], reverse=True)
        
        # Top 10 Doctors
        top_doctors = doctor_stats[:10]
        top_doctors_labels = [d['name'] for d in top_doctors]
        top_doctors_data = [d['visits'] for d in top_doctors]
        top_doctors_visited = [d['visited_count'] for d in top_doctors]
        top_doctors_not_visited = [d['not_visited_count'] for d in top_doctors]
        
        # Status Distribution
        if 'Estatus' in df.columns:
            status_counts = df['Estatus'].value_counts().reset_index()
            status_labels = status_counts['Estatus'].tolist()
            status_data = status_counts['count'].tolist()
        else:
            status_labels = []
            status_data = []

        # JSON Data for JS
        data_json = json.dumps({
            'total_visits': total_visits,
            'unique_doctors': unique_doctors,
            'avg_duration_mins': avg_duration_mins,
            'avg_visits_per_day': avg_visits_per_day,
            'monthly_labels': monthly_labels,
            'monthly_data': monthly_data,
            'status_labels': status_labels,
            'status_data': status_data,
            'top_doctors_labels': top_doctors_labels,
            'top_doctors_data': top_doctors_data,
            'top_doctors_visited': top_doctors_visited,
            'top_doctors_not_visited': top_doctors_not_visited,
            'doctors': doctor_stats
        }, default=str)

        # HTML Template with Modular Layout
        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Visitas Angel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style type="text/tailwindcss">
        body {{ font-family: 'Outfit', sans-serif; background-color: #0f172a; color: #e2e8f0; }}
        .glass {{ background: rgba(30, 41, 59, 0.4); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.05); }}
        .card {{ @apply glass rounded-2xl p-6 shadow-xl transition-all duration-300 hover:bg-slate-800/50; }}
        .sidebar-link {{ @apply flex items-center gap-3 px-4 py-3 rounded-xl text-slate-400 hover:text-blue-300 hover:bg-blue-600/20 hover:border hover:border-blue-500/30 transition-all cursor-pointer; }}
        .sidebar-link.active {{ @apply bg-blue-600/10 text-blue-400 border border-blue-500/20; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; animation: fadeIn 0.3s ease-in-out; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        
        /* Table Styles */
        th {{ @apply text-left p-4 text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-slate-700/50; }}
        td {{ @apply p-4 border-b border-slate-800/50 text-sm; }}
        tr:hover td {{ @apply bg-slate-800/30; }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #475569; }}

        /* Mobile Adjustments */
        @media (max-width: 768px) {{
            .mobile-sidebar-open {{ transform: translateX(0); }}
            .mobile-sidebar-closed {{ transform: translateX(-100%); }}
        }}
    </style>
</head>
<body class="h-screen flex overflow-hidden bg-[#0B1120]">
    
    <!-- Mobile Header -->
    <div class="md:hidden fixed top-0 w-full z-40 bg-[#0f172a]/90 backdrop-blur border-b border-slate-800/50 p-4 flex justify-between items-center">
        <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
                <i data-lucide="activity" class="text-white w-4 h-4"></i>
            </div>
            <span class="font-bold text-white">Visitas Angel</span>
        </div>
        <button onclick="toggleSidebar()" class="text-white p-2 hover:bg-slate-800 rounded-lg">
            <i data-lucide="menu" class="w-6 h-6"></i>
        </button>
    </div>

    <!-- Sidebar Wrapper -->
    <!-- Mobile: Fixed full screen, initially hidden off-screen. Desktop: Relative, visible -->
    <aside id="sidebar" class="fixed inset-0 z-50 md:relative md:z-auto w-64 transform -translate-x-full md:translate-x-0 transition-transform duration-300 ease-in-out md:flex md:flex-col bg-[#0f172a] border-r border-slate-800/50 flex-shrink-0">
        <!-- Close Button Mobile -->
        <div class="md:hidden absolute top-4 right-4">
            <button onclick="toggleSidebar()" class="text-slate-400 p-2 hover:bg-slate-800 rounded-lg">
                <i data-lucide="x" class="w-6 h-6"></i>
            </button>
        </div>

        <div class="p-6 h-full flex flex-col">
            <div class="hidden md:flex items-center gap-3 mb-8">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                    <i data-lucide="activity" class="text-white"></i>
                </div>
                <div>
                    <h1 class="font-bold text-lg text-white leading-tight">Visitas Angel</h1>
                    <p class="text-xs text-slate-500">MTP Analytics</p>
                </div>
            </div>
            
            <nav class="space-y-2 flex-1">
                <div class="sidebar-link active" onclick="switchTab('dashboard', this)">
                    <i data-lucide="layout-dashboard" class="w-5 h-5"></i>
                    <span>Dashboard</span>
                </div>
                <div class="sidebar-link" onclick="switchTab('doctors', this)">
                    <i data-lucide="users" class="w-5 h-5"></i>
                    <span>Médicos</span>
                </div>
            </nav>
            
            <div class="mt-auto pt-6 border-t border-slate-800/50">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-slate-700 border border-slate-600"></div>
                    <div>
                        <p class="text-sm font-medium text-white">Angel Pari</p>
                        <p class="text-xs text-slate-500">Representante</p>
                    </div>
                </div>
            </div>
        </div>
    </aside>

    <!-- Overlay for Mobile Sidebar -->
    <div id="sidebarOverlay" onclick="toggleSidebar()" class="fixed inset-0 bg-black/50 z-40 hidden md:hidden glass transition-opacity"></div>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto bg-gradient-to-br from-[#0f172a] to-[#1e293b] pt-16 md:pt-0">
        <div class="max-w-7xl mx-auto p-4 md:p-8 font-sans">
            
            <!-- Dashboard View -->
            <div id="dashboard" class="tab-content active space-y-6">
                <div class="flex justify-between items-end mb-2">
                    <div>
                        <h2 class="text-2xl md:text-3xl font-bold text-white mb-1">Resumen General</h2>
                        <p class="text-slate-400 text-sm">Panorama actual de visitas y cobertura médica.</p>
                    </div>
                </div>

                <!-- KPI Cards -->
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
                    <div class="card bg-gradient-to-br from-slate-800/50 to-slate-900/50 border-t border-blue-500/20 relative overflow-hidden group">
                        <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <i data-lucide="layers" class="w-16 h-16 text-blue-400"></i>
                        </div>
                        <p class="text-slate-400 text-sm font-medium mb-1">Total Visitas</p>
                        <h3 class="text-4xl font-bold text-white" id="totalVisits">0</h3>
                        <div class="mt-4 flex items-center text-emerald-400 text-sm">
                            <i data-lucide="calendar-check" class="w-4 h-4 mr-1"></i>
                            <span>2024-2025</span>
                        </div>
                    </div>
                    
                    <div class="card bg-gradient-to-br from-slate-800/50 to-slate-900/50 border-t border-indigo-500/20 relative overflow-hidden group">
                        <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <i data-lucide="users" class="w-16 h-16 text-indigo-400"></i>
                        </div>
                        <p class="text-slate-400 text-sm font-medium mb-1">Médicos Únicos</p>
                        <h3 class="text-4xl font-bold text-white" id="uniqueDoctors">0</h3>
                        <div class="mt-4 flex items-center text-blue-400 text-sm">
                            <i data-lucide="user-check" class="w-4 h-4 mr-1"></i>
                            <span>Cartera Activa</span>
                        </div>
                    </div>

                     <div class="card bg-gradient-to-br from-slate-800/50 to-slate-900/50 border-t border-amber-500/20 relative overflow-hidden group">
                        <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <i data-lucide="clock" class="w-16 h-16 text-amber-400"></i>
                        </div>
                        <p class="text-slate-400 text-sm font-medium mb-1">Promedio Duración</p>
                        <div class="flex items-baseline gap-2">
                             <h3 class="text-4xl font-bold text-white" id="avgDuration">0</h3>
                             <span class="text-sm text-slate-500 font-medium">min</span>
                        </div>
                        <div class="mt-4 flex items-center text-amber-400 text-sm">
                            <i data-lucide="timer" class="w-4 h-4 mr-1"></i>
                            <span>Por visita</span>
                        </div>
                    </div>

                    <div class="card bg-gradient-to-br from-slate-800/50 to-slate-900/50 border-t border-purple-500/20 relative overflow-hidden group">
                         <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <i data-lucide="briefcase" class="w-16 h-16 text-purple-400"></i>
                        </div>
                        <p class="text-slate-400 text-sm font-medium mb-1">Visitas / Día</p>
                        <h3 class="text-4xl font-bold text-white" id="avgVisitsDay">0</h3>
                        <div class="mt-4 flex items-center text-purple-400 text-sm">
                            <i data-lucide="trending-up" class="w-4 h-4 mr-1"></i>
                            <span>Promedio diario</span>
                        </div>
                    </div>
                </div>

                <!-- Charts Section -->
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <!-- Monthly Chart with Strict Container -->
                    <div class="card col-span-1 lg:col-span-2 flex flex-col">
                        <h3 class="text-lg font-semibold text-white mb-4">Tendencia de Visitas</h3>
                        <div class="relative h-64 w-full flex-1 min-h-[250px]"> <!-- Container height enforced -->
                            <canvas id="monthlyChart"></canvas>
                        </div>
                    </div>
                    
                    <!-- Status Chart -->
                    <div class="card flex flex-col">
                        <h3 class="text-lg font-semibold text-white mb-4">Estatus</h3>
                        <div class="relative h-64 w-full flex-1 min-h-[250px] flex justify-center items-center">
                             <canvas id="statusChart"></canvas>
                        </div>
                    </div>

                    <!-- Top 10 Doctors Chart -->
                    <div class="card col-span-1 lg:col-span-3 flex flex-col">
                        <h3 class="text-lg font-semibold text-white mb-4">Top 10 Médicos con Más Interacciones</h3>
                        <div class="relative h-80 w-full flex-1 min-h-[300px]">
                            <canvas id="topDoctorsChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Doctors View -->
            <div id="doctors" class="tab-content space-y-6">
                <!-- Header with search -->
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center bg-slate-800/50 p-4 rounded-xl border border-slate-700/50 gap-4">
                    <div>
                        <h2 class="text-2xl font-bold text-white">Cartera de Médicos</h2>
                    </div>
                    <div class="relative w-full md:w-auto">
                        <input type="text" id="searchInput" onkeyup="filterDoctors()" placeholder="Buscar médico..." class="bg-slate-900 border border-slate-700 rounded-lg pl-10 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500 w-full md:w-64 shadow-inner">
                        <i data-lucide="search" class="w-4 h-4 text-slate-500 absolute left-3 top-2.5"></i>
                    </div>
                </div>

                <div class="card overflow-hidden p-0 border border-slate-700/50">
                    <div class="overflow-x-auto max-h-[65vh]">
                        <table class="w-full whitespace-nowrap">
                            <thead class="bg-slate-900/80 sticky top-0 z-10 backdrop-blur-md">
                                <tr>
                                    <th class="w-1/3">Médico</th>
                                    <th>Frecuencia</th>
                                    <th>Última Interacción</th>
                                    <th>Estado Reciente</th>
                                    <th class="text-right">Detalle</th>
                                </tr>
                            </thead>
                            <tbody id="doctorsTableBody" class="divide-y divide-slate-800/50">
                                <!-- Dynamic Content -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- Modal -->
    <div id="modal" class="fixed inset-0 bg-black/90 hidden backdrop-blur-md z-50 transition-opacity duration-300 opacity-0 pointer-events-none flex items-center justify-center p-4">
        <div class="bg-[#1e293b] border border-slate-700 rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl transform transition-all scale-95 duration-300" id="modalPanel">
            <!-- Modal Header -->
            <div class="p-4 md:p-6 border-b border-slate-700/50 flex justify-between items-center bg-slate-800/50 rounded-t-2xl flex-shrink-0">
                <div class="flex items-center gap-3 md:gap-4">
                    <div class="w-10 h-10 md:w-12 md:h-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 font-bold text-lg shadow-inner">
                        <i data-lucide="user"></i>
                    </div>
                    <div>
                        <h2 class="text-lg md:text-xl font-bold text-white flex items-center gap-2" id="modalTitle">
                            Historial
                        </h2>
                        <span class="text-xs text-slate-400 px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700">Timeline de interacciones</span>
                    </div>
                </div>
                <button onclick="closeModal()" class="p-2 hover:bg-red-500/10 hover:text-red-400 rounded-lg transition-colors text-slate-400">
                    <i data-lucide="x" class="w-6 h-6"></i>
                </button>
            </div>
            
            <!-- Modal Content -->
            <div class="p-4 md:p-6 overflow-y-auto space-y-6" id="modalContent">
                <!-- History Items -->
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();
        const data = {data_json};

        // Sidebar Toggle Logic
        function toggleSidebar() {{
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('sidebarOverlay');
            
            sidebar.classList.toggle('-translate-x-full');
            
            if (sidebar.classList.contains('-translate-x-full')) {{
                overlay.classList.add('hidden');
            }} else {{
                overlay.classList.remove('hidden');
            }}
        }}

        // Navigation
        function switchTab(tabId, element) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
            if(element) element.classList.add('active');
            
            // Close sidebar on mobile after selection
            if (window.innerWidth < 768) {{
                toggleSidebar();
            }}
        }}

        // Filter Logic
        function filterDoctors() {{
            const input = document.getElementById('searchInput');
            const filter = input.value.toLowerCase();
            const rows = document.getElementById('doctorsTableBody').getElementsByTagName('tr');
            
            for (let i = 0; i < rows.length; i++) {{
                const nameCol = rows[i].getElementsByTagName('td')[0];
                if (nameCol) {{
                    const txtValue = nameCol.textContent || nameCol.innerText;
                    if (txtValue.toLowerCase().indexOf(filter) > -1) {{
                        rows[i].style.display = "";
                    }} else {{
                        rows[i].style.display = "none";
                    }}
                }}
            }}
        }}

        // Init Metrics
        document.getElementById('totalVisits').innerText = data.total_visits;
        document.getElementById('uniqueDoctors').innerText = data.unique_doctors;
        document.getElementById('avgDuration').innerText = data.avg_duration_mins || '-';
        document.getElementById('avgVisitsDay').innerText = data.avg_visits_per_day || '-';

        // Charts Config
        Chart.defaults.color = '#64748b';
        Chart.defaults.borderColor = '#334155';
        
        const customTooltip = {{
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            titleColor: '#f8fafc',
            bodyColor: '#e2e8f0',
            padding: 12,
            borderColor: 'rgba(51, 65, 85, 0.5)',
            borderWidth: 1,
            displayColors: true,
            cornerRadius: 8,
            boxPadding: 4
        }};

        // Monthly Chart
        const ctxMonthly = document.getElementById('monthlyChart').getContext('2d');
        new Chart(ctxMonthly, {{
            type: 'bar',
            data: {{
                labels: data.monthly_labels,
                datasets: [{{
                    label: 'Visitas',
                    data: data.monthly_data,
                    backgroundColor: 'rgba(59, 130, 246, 0.8)',
                    hoverBackgroundColor: '#3b82f6',
                    borderRadius: 4,
                    maxBarThickness: 40 // Prevent overly wide bars
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false, // Important: allows filling container height
                animation: {{ duration: 500 }}, // Reduce animation load
                plugins: {{ 
                    legend: {{ display: false }}, 
                    tooltip: customTooltip 
                }},
                scales: {{ 
                    y: {{ 
                        beginAtZero: true, 
                        grid: {{ borderDash: [4, 4], color: '#334155' }},
                        ticks: {{ font: {{ size: 11 }} }}
                    }},
                    x: {{ 
                        grid: {{ display: false }},
                        ticks: {{ font: {{ size: 11 }} }}
                    }}
                }}
            }}
        }});

        // Status Chart
        new Chart(document.getElementById('statusChart').getContext('2d'), {{
            type: 'doughnut',
            data: {{
                labels: data.status_labels,
                datasets: [{{
                    data: data.status_data,
                    backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
                    borderWidth: 0,
                    hoverOffset: 10
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                animation: {{ duration: 800 }},
                plugins: {{ 
                    legend: {{ position: 'bottom', labels: {{ usePointStyle: true, padding: 15, font: {{ size: 11 }} }} }}, 
                    tooltip: customTooltip 
                }}
            }}
        }});

        // Top 10 Doctors Chart (Reverted to Bar with Custom Tooltip)
        const ctxTop = document.getElementById('topDoctorsChart').getContext('2d');
        new Chart(ctxTop, {{
            type: 'bar',
            data: {{
                labels: data.top_doctors_labels,
                datasets: [{{
                    label: 'Visitas',
                    data: data.top_doctors_data,
                    backgroundColor: 'rgba(139, 92, 246, 0.8)', // Violet/Purple
                    hoverBackgroundColor: '#8b5cf6',
                    borderRadius: 4,
                    barThickness: 20
                }}]
            }},
            options: {{
                indexAxis: 'y', // Horizontal
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ 
                    legend: {{ display: false }}, 
                    tooltip: {{
                        ...customTooltip,
                        callbacks: {{
                            label: function(context) {{
                                const index = context.dataIndex;
                                const total = context.raw;
                                const visited = data.top_doctors_visited[index];
                                const notVisited = data.top_doctors_not_visited[index];
                                return [
                                    `Total: ${{total}}`,
                                    `Visitados: ${{visited}}`,
                                    `No Visitados: ${{notVisited}}`
                                ];
                            }}
                        }}
                    }}
                }},
                scales: {{ 
                    x: {{ 
                        beginAtZero: true,
                        grid: {{ borderDash: [4, 4], color: '#334155' }},
                        ticks: {{ font: {{ size: 11 }} }}
                    }},
                    y: {{ 
                        grid: {{ display: false }},
                        ticks: {{ font: {{ size: 11, weight: 500 }} }}
                    }}
                }}
            }}
        }});


        // Render Table
        const tbody = document.getElementById('doctorsTableBody');
        data.doctors.forEach((doc, index) => {{
            const tr = document.createElement('tr');
            const recentStatus = doc.history.length > 0 ? doc.history[0].Estatus : 'N/A';
            
            let statusBadge = '';
            const st = (recentStatus || '').toLowerCase();
            if (st.includes('no visitado')) statusBadge = '<span class="px-2 py-1 rounded-full text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/20">No Visita</span>';
            else if (st.includes('reprogramado')) statusBadge = '<span class="px-2 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">Reprogr.</span>';
            else if (st.includes('visitado')) statusBadge = '<span class="px-2 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Visitado</span>';
            else statusBadge = `<span class="px-2 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">${{recentStatus || 'N/A'}}</span>`;

            tr.innerHTML = `
                <td>
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-400 border border-slate-700">
                            ${{doc.name.charAt(0)}}
                        </div>
                        <span class="font-medium text-slate-200">${{doc.name}}</span>
                    </div>
                </td>
                <td>
                    <div class="flex items-center gap-2">
                        <span class="text-sm font-semibold w-6 text-right">${{doc.visits}}</span>
                        <div class="w-24 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div class="h-full bg-blue-500" style="width: ${{Math.min((doc.visits/15)*100, 100)}}%"></div>
                        </div>
                    </div>
                </td>
                <td class="text-slate-400 text-xs">${{doc.last_visit}}</td>
                <td>
                    ${{statusBadge}}
                </td>
                <td class="text-right">
                    <button onclick="showHistory(${{index}})" class="group flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-lg transition-all text-xs font-medium border border-blue-500/20 hover:border-blue-500/40">
                        <span class="hidden md:inline">Ver Historial</span>
                        <span class="md:hidden">Ver</span>
                        <i data-lucide="arrow-right" class="w-3 h-3 transition-transform group-hover:translate-x-0.5"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        }});

        // Modal Logic
        const modal = document.getElementById('modal');
        const modalPanel = document.getElementById('modalPanel');

        function showHistory(index) {{
            const doc = data.doctors[index];
            if (!doc) return;

            document.getElementById('modalTitle').innerText = doc.name;
            const content = document.getElementById('modalContent');
            content.innerHTML = '';
            
            if (doc.history.length === 0) {{
                content.innerHTML = '<div class="text-center text-slate-500 py-8">No hay historial disponible</div>';
            }}

            doc.history.forEach((h, idx) => {{
                const isLast = idx === doc.history.length - 1;
                
                // Photo Handling
                const hasPhoto = h.Foto && h.Foto.length > 3 && h.Foto.toLowerCase() !== 'nan';
                const photoHtml = hasPhoto
                    ? `<div class="mt-4 group relative rounded-lg overflow-hidden border border-slate-700/50 bg-black/40">
                         <img src="${{h.Foto}}" loading="lazy" class="w-full h-auto object-contain max-h-[400px] bg-[#0f172a]" alt="Evidencia">
                         <div class="absolute top-2 right-2 px-2 py-1 bg-black/60 backdrop-blur rounded text-[10px] text-white/80 font-mono border border-white/10">
                            ${{h.Foto}}
                         </div>
                       </div>` 
                    : '';

                const item = document.createElement('div');
                item.className = 'relative pl-8 pb-8';
                
                // Custom Icon based on status
                let iconClass = 'bg-blue-500';
                if(String(h.Estatus).toLowerCase().includes('no')) iconClass = 'bg-red-500';
                if(String(h.Estatus).toLowerCase().includes('reprogramado')) iconClass = 'bg-amber-500';
                
                item.innerHTML = `
                    ${{!isLast ? '<div class="absolute left-[11px] top-6 bottom-0 w-px bg-slate-700/50 dashed"></div>' : ''}}
                    <div class="absolute left-0 top-1.5 w-6 h-6 rounded-full border-4 border-[#1e293b] ${{iconClass}} z-10 shadow-lg shadow-${{iconClass.replace('bg-', '')}}-500/20"></div>
                    
                    <div class="bg-slate-800/40 p-5 rounded-xl border border-slate-700/50 hover:bg-slate-800/60 transition-all duration-300 hover:shadow-lg hover:shadow-black/20 hover:border-slate-600/50">
                        <div class="flex justify-between items-start mb-3 border-b border-slate-700/30 pb-3">
                            <span class="text-sm font-bold text-slate-200 flex items-center gap-2">
                                <i data-lucide="calendar" class="w-4 h-4 text-slate-400"></i>
                                ${{h['Fecha de visita']}}
                            </span>
                            <span class="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded text-slate-300 bg-slate-700/50 border border-slate-600">
                                ${{h.Estatus || 'Registro'}}
                            </span>
                        </div>
                        
                        <div class="space-y-3">
                             <div>
                                <h5 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Comentario</h5>
                                <p class="text-slate-300 text-sm leading-relaxed">${{h.Comentario || 'Sin comentario registrado.'}}</p>
                             </div>
                             ${{photoHtml ? `
                             <div>
                                <h5 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1 flex items-center gap-2">
                                    <i data-lucide="image" class="w-3 h-3"></i> Evidencia Fotográfica
                                </h5>
                                ${{photoHtml}}
                             </div>` : ''}}
                        </div>
                    </div>
                `;
                content.appendChild(item);
            }});
            
            modal.classList.remove('hidden', 'pointer-events-none');
            // Small delay to allow display:block to apply before opacity transition
            setTimeout(() => {{
                modal.classList.remove('opacity-0');
                modalPanel.classList.remove('scale-95');
                modalPanel.classList.add('scale-100');
            }}, 50);
            lucide.createIcons();
        }}

        function closeModal() {{
            modal.classList.add('opacity-0');
            modalPanel.classList.add('scale-95');
            setTimeout(() => {{
                modal.classList.add('hidden', 'pointer-events-none');
            }}, 300);
        }}
        
        modal.addEventListener('click', (e) => {{
            if (e.target.id === 'modal') closeModal();
        }});
        
        // Escape key to close
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeModal();
        }});
    </script>
</body>
</html>"""
        
        with open('angel_dashboard.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print("Dashboard generated successfully: angel_dashboard.html")
        
    except Exception as e:
        print(f"Error generating dashboard: {e}")

if __name__ == "__main__":
    generate_dashboard()
