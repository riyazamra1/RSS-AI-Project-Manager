package com.riyaz.rssaiprojectmanager

import android.os.Bundle
import android.content.Context
import androidx.activity.ComponentActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.foundation.Image
import androidx.compose.ui.Alignment
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.runtime.*
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.geometry.Offset
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import coil.compose.AsyncImage
import androidx.compose.ui.res.painterResource
import androidx.compose.foundation.clickable
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

private class ProjectManagerApi(private val baseUrl: String) {
    private val client = OkHttpClient()
    var token: String? = null
    var workspaceId: String? = null

    private fun request(path: String, method: String, body: String? = null): String {
        val builder = Request.Builder()
            .url(baseUrl.trimEnd('/') + path)
            .addHeader("Accept", "application/json")
        token?.let { builder.addHeader("Authorization", "Bearer $it") }
        workspaceId?.let { builder.addHeader("X-Workspace-ID", it) }
        if (body != null) {
            builder.method(method, body.toRequestBody("application/json".toMediaType()))
        } else {
            builder.method(method, null)
        }
        client.newCall(builder.build()).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) error("HTTP ${response.code}: ${text.take(500)}")
            return text
        }
    }

    fun login(email: String, password: String): JSONObject =
        JSONObject(request("/auth/login", "POST", JSONObject().put("email", email).put("password", password).toString()))

    fun register(name: String, email: String, password: String, workspaceName: String): JSONObject =
        JSONObject(request("/auth/register", "POST", JSONObject().put("full_name", name).put("email", email).put("password", password).put("workspace_name", workspaceName).toString()))

    fun projects(): JSONArray = JSONArray(request("/api/v1/projects", "GET"))

    fun updateProject(id: String, name: String, repository: String?, description: String): JSONObject {
        val body = JSONObject()
            .put("name", name)
            .put("enabled", true)
            .put("priority", 100)
            .put("description", description)
        if (!repository.isNullOrBlank()) body.put("repository", repository)
        else body.put("repository", JSONObject.NULL)
        return JSONObject(request("/api/v1/projects/$id", "PATCH", body.toString()))
    }

    fun createProject(id: String, name: String, repository: String?, description: String): JSONObject {
        val body = JSONObject()
            .put("id", id)
            .put("name", name)
            .put("enabled", true)
            .put("priority", 100)
            .put("description", description)
        if (!repository.isNullOrBlank()) body.put("repository", repository)
        return JSONObject(request("/api/v1/projects", "POST", body.toString()))
    }

    fun tasks(projectId: String): JSONArray =
        JSONArray(request("/api/v1/tasks?project_id=$projectId", "GET"))

    fun createTask(title: String, projectId: String, context: String): JSONObject {
        val body = JSONObject()
            .put("title", title)
            .put("project_id", projectId)
        if (context.isNotBlank()) body.put("context", context)
        return JSONObject(request("/api/v1/tasks", "POST", body.toString()))
    }

    fun goAhead(): JSONObject = JSONObject(request("/api/v1/tasks/run-next-user", "POST"))

    fun logout(): JSONObject = JSONObject(request("/auth/logout", "POST"))
}

data class Project(
    val id: String,
    val name: String,
    val repository: String?,
    val status: String?,
    val description: String?
)

data class Task(val id: String, val title: String, val status: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ProjectManagerApp() }
    }
}

@Composable
private fun ProjectManagerApp() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val securePrefs = remember {
        EncryptedSharedPreferences.create(
            "rss_pm_session",
            MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC),
            context,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }
    var baseUrl by remember { mutableStateOf("https://pm.rssapps.cv") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var workspaceId by remember { mutableStateOf(securePrefs.getString("workspace_id", null)) }
    var signedIn by remember { mutableStateOf(securePrefs.getString("token", null) != null) }
    var introSeen by remember { mutableStateOf(securePrefs.getBoolean("intro_seen", false)) }
    var authTab by remember { mutableStateOf("login") }
    var registerName by remember { mutableStateOf("") }
    var registerEmail by remember { mutableStateOf("") }
    var registerPassword by remember { mutableStateOf("") }
    var registerConfirm by remember { mutableStateOf("") }
    var registerWorkspace by remember { mutableStateOf("My RSS Workspace") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    val api = remember(baseUrl) { ProjectManagerApi(baseUrl).also { it.token = securePrefs.getString("token", null); it.workspaceId = workspaceId } }
    val scope = rememberCoroutineScope()

    var projects by remember { mutableStateOf(emptyList<Project>()) }
    var selected by remember { mutableStateOf<Project?>(null) }
    var tasks by remember { mutableStateOf(emptyList<Task>()) }

    var taskTitle by remember { mutableStateOf("") }
    var taskContext by remember { mutableStateOf("") }

    var showProjectForm by remember { mutableStateOf(false) }
    var editingProject by remember { mutableStateOf<Project?>(null) }
    var projectId by remember { mutableStateOf("") }
    var projectName by remember { mutableStateOf("") }
    var projectRepo by remember { mutableStateOf("") }
    var projectDescription by remember { mutableStateOf("") }

    fun loadProjects() {
        scope.launch(Dispatchers.IO) {
            try {
                val json = api.projects()
                projects = (0 until json.length()).map { i ->
                    json.getJSONObject(i).let {
                        Project(
                            it.getString("id"),
                            it.getString("name"),
                            it.optString("repository").ifBlank { null },
                            it.optString("status").ifBlank { null },
                            it.optString("description").ifBlank { null }
                        )
                    }
                }
                error = null
            } catch (e: Exception) {
                error = e.message
            }
        }
    }

    fun loadTasks(project: Project) {
        scope.launch(Dispatchers.IO) {
            try {
                val json = api.tasks(project.id)
                tasks = (0 until json.length()).map { i ->
                    json.getJSONObject(i).let {
                        Task(
                            it.getLong("id").toString(),
                            it.getString("title"),
                            it.getString("status")
                        )
                    }
                }
                error = null
            } catch (e: Exception) {
                error = e.message
            }
        }
    }

    LaunchedEffect(signedIn) {
        if (signedIn) loadProjects()
    }

    MaterialTheme {
        Surface(Modifier.fillMaxSize()) {
            if (!introSeen) {
                IntroFlowScreen(onFinish = {
                    introSeen = true
                    securePrefs.edit().putBoolean("intro_seen", true).apply()
                })
            } else if (!signedIn) {
                AuthScreen(
                    tab = authTab,
                    onTab = { authTab = it; error = null },
                    baseUrl = baseUrl, onBaseUrl = { baseUrl = it },
                    loginEmail = email, onLoginEmail = { email = it },
                    loginPassword = password, onLoginPassword = { password = it },
                    registerName = registerName, onRegisterName = { registerName = it },
                    registerEmail = registerEmail, onRegisterEmail = { registerEmail = it },
                    registerPassword = registerPassword, onRegisterPassword = { registerPassword = it },
                    registerConfirm = registerConfirm, onRegisterConfirm = { registerConfirm = it },
                    registerWorkspace = registerWorkspace, onRegisterWorkspace = { registerWorkspace = it },
                    error = error, busy = busy,
                    onLogin = {
                        if (email.isBlank() || password.isBlank()) { error = "Enter email and password."; return@AuthScreen }
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                val result = api.login(email.trim(), password)
                                api.token = result.getString("access_token")
                                val workspace = result.optJSONObject("workspace")
                                api.workspaceId = workspace?.getString("id") ?: result.optJSONArray("workspaces")?.takeIf { it.length() > 0 }?.getJSONObject(0)?.getString("id")
                                if (api.workspaceId.isNullOrBlank()) error = "No active workspace returned by server."
                                else {
                                    securePrefs.edit().putString("token", api.token).putString("workspace_id", api.workspaceId).apply()
                                    workspaceId = api.workspaceId; signedIn = true; error = null
                                }
                            } catch (e: Exception) { error = e.message ?: "Sign in failed." }
                            finally { busy = false }
                        }
                    },
                    onRegister = {
                        val name = registerName.trim(); val mail = registerEmail.trim(); val workspace = registerWorkspace.trim()
                        when {
                            name.isBlank() -> error = "Enter your full name."
                            mail.isBlank() || !mail.contains("@") -> error = "Enter a valid email address."
                            registerPassword.length < 12 -> error = "Password must be at least 12 characters."
                            registerPassword != registerConfirm -> error = "Passwords do not match."
                            workspace.isBlank() -> error = "Enter a workspace name."
                            else -> {
                                busy = true
                                scope.launch(Dispatchers.IO) {
                                    try {
                                        val result = api.register(name, mail, registerPassword, workspace)
                                        error = result.optString("message", "Account request submitted. Check your email and wait for administrator approval.")
                                        email = mail; password = ""; registerPassword = ""; registerConfirm = ""
                                        authTab = "login"
                                    } catch (e: Exception) { error = e.message ?: "Registration failed." }
                                    finally { busy = false }
                                }
                            }
                        }
                    }
                )
            } else {
                Dashboard(
                    projects = projects,
                    selected = selected,
                    tasks = tasks,
                    taskTitle = taskTitle,
                    onTaskTitle = { taskTitle = it },
                    taskContext = taskContext,
                    onTaskContext = { taskContext = it },
                    onSelect = {
                        selected = it
                        loadTasks(it)
                    },
                    onCreate = {
                        val project = selected ?: return@Dashboard
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                api.createTask(taskTitle.trim(), project.id, taskContext)
                                taskTitle = ""
                                taskContext = ""
                                loadTasks(project)
                                error = null
                            } catch (e: Exception) {
                                error = e.message
                            } finally {
                                busy = false
                            }
                        }
                    },
                    onGoAhead = {
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                val result = api.goAhead()
                                error = "Execution: ${result.optString("status", "unknown")}  Task: ${result.optString("task_id", "none")}"
                                selected?.let { loadTasks(it) }
                            } catch (e: Exception) {
                                error = e.message
                            } finally {
                                busy = false
                            }
                        }
                    },
                    onLogout = {
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try { api.logout() } catch (_: Exception) { /* local session is still cleared */ }
                            securePrefs.edit().clear().apply()
                            api.token = null
                            api.workspaceId = null
                            workspaceId = null
                            signedIn = false
                            selected = null
                            projects = emptyList()
                            tasks = emptyList()
                            busy = false
                        }
                    },
                    onRefresh = {
                        loadProjects()
                        selected?.let { loadTasks(it) }
                    },
                    busy = busy,                    error = error,
                    onCreateProject = { id, name, repo, description ->
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                api.createProject(id.trim(), name.trim(), repo.trim().ifBlank { null }, description)
                                showProjectForm = false
                                projectId = ""
                                projectName = ""
                                projectRepo = ""
                                projectDescription = ""
                                loadProjects()
                                error = null
                            } catch (e: Exception) {
                                error = e.message
                            } finally {
                                busy = false
                            }
                        }
                    },
                    onEditProject = {
                        editingProject = it
                        projectName = it.name
                        projectRepo = it.repository.orEmpty()
                        projectDescription = it.description.orEmpty()
                    },
                    onUpdateProject = { p, name, repo, description ->
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                api.updateProject(p.id, name.trim(), repo.trim().ifBlank { null }, description)
                                editingProject = null
                                loadProjects()
                                selected = null
                                error = null
                            } catch (e: Exception) {
                                error = e.message
                            } finally {
                                busy = false
                            }
                        }
                    },
                    showProjectForm = showProjectForm,
                    onShowProjectForm = { showProjectForm = true },
                    onDismissProjectForm = { showProjectForm = false },
                    editingProject = editingProject,
                    onDismissEdit = { editingProject = null },
                    projectId = projectId,
                    onProjectId = { projectId = it },
                    projectName = projectName,
                    onProjectName = { projectName = it },
                    projectRepo = projectRepo,
                    onProjectRepo = { projectRepo = it },
                    projectDescription = projectDescription,
                    onProjectDescription = { projectDescription = it }
                )
            }
        }
    }
}

@Composable
private fun AnimatedRoyalBackground(content: @Composable BoxScope.() -> Unit) {
    val transition = rememberInfiniteTransition(label = "rssRoyal")
    val shift by transition.animateFloat(-900f, 1800f, infiniteRepeatable(tween(9000, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "shift")
    val gradient = Brush.linearGradient(
        listOf(Color(0xFF283593), Color(0xFF7E57C2), Color(0xFF00ACC1), Color(0xFF26A69A), Color(0xFFE0F7FA)),
        Offset(0f, shift), Offset(1200f, shift + 1200f)
    )
    Box(Modifier.fillMaxSize().background(gradient), content = content)
}

@Composable
private fun IntroFlowScreen(onFinish: () -> Unit) {
    var page by remember { mutableStateOf(0) }
    val titles = listOf("Manage Every RSS Project", "Turn Requirements Into Tasks", "Let AI Execute", "Track Progress Clearly")
    val bodies = listOf("One command center for your RSS project portfolio.", "Capture requirements, priorities and next actions in one place.", "Connect RSS Core and automation so approved work can move forward.", "Monitor projects, tasks and execution status from your dashboard.")
    AnimatedRoyalBackground {
        Column(Modifier.fillMaxSize().padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Image(painter = painterResource(R.drawable.rss_ai_project_manager_logo), contentDescription = "RSS AI Project Manager logo", modifier = Modifier.size(190.dp), contentScale = ContentScale.Fit)
            Spacer(Modifier.height(28.dp))
            Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(30.dp), colors = CardDefaults.cardColors(Color.White.copy(alpha=.96f))) {
                Column(Modifier.padding(26.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    Text(titles[page], style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Color(0xFF182052), textAlign = TextAlign.Center)
                    Text(bodies[page], textAlign = TextAlign.Center, color = Color(0xFF5F6368))
                    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) { repeat(titles.size) { Text(if (it == page) "●" else "○", color = Color(0xFF3949AB)) } }
                    Button(onClick = { if (page == titles.lastIndex) onFinish() else page++ }, Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(16.dp)) { Text(if (page == titles.lastIndex) "Get Started" else "Next") }
                    if (page < titles.lastIndex) TextButton(onClick = onFinish) { Text("Skip") }
                }
            }
        }
    }
}

@Composable
private fun AuthScreen(
    tab: String, onTab: (String) -> Unit,
    baseUrl: String, onBaseUrl: (String) -> Unit,
    loginEmail: String, onLoginEmail: (String) -> Unit,
    loginPassword: String, onLoginPassword: (String) -> Unit,
    registerName: String, onRegisterName: (String) -> Unit,
    registerEmail: String, onRegisterEmail: (String) -> Unit,
    registerPassword: String, onRegisterPassword: (String) -> Unit,
    registerConfirm: String, onRegisterConfirm: (String) -> Unit,
    registerWorkspace: String, onRegisterWorkspace: (String) -> Unit,
    error: String?, busy: Boolean, onLogin: () -> Unit, onRegister: () -> Unit
) {
    var policyAccepted by remember { mutableStateOf(false) }
    AnimatedRoyalBackground {
        Column(Modifier.fillMaxSize().padding(horizontal = 22.dp, vertical = 24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Image(painter = painterResource(R.drawable.rss_ai_project_manager_logo), contentDescription = "RSS AI Project Manager logo", modifier = Modifier.size(width = 150.dp, height = 92.dp), contentScale = ContentScale.Fit)
            Text("RSS AI PROJECT MANAGER", color=Color.White, fontWeight=FontWeight.Bold)
            Spacer(Modifier.height(14.dp))
            Card(Modifier.fillMaxWidth(), shape=RoundedCornerShape(28.dp), colors=CardDefaults.cardColors(Color.White.copy(alpha=.97f)), elevation=CardDefaults.cardElevation(10.dp)) {
                Column(Modifier.padding(22.dp), verticalArrangement=Arrangement.spacedBy(11.dp)) {
                    Text("Welcome to RSS AI Project Manager", style=MaterialTheme.typography.headlineSmall, fontWeight=FontWeight.Bold, color=Color(0xFF182052), textAlign=TextAlign.Center, modifier=Modifier.fillMaxWidth())
                    Row(Modifier.fillMaxWidth().background(Color(0xFFE8EAF6), RoundedCornerShape(16.dp)).padding(4.dp)) {
                        listOf("login" to "Sign In", "register" to "Create Account").forEach { (key,label) ->
                            Button(onClick={onTab(key)}, Modifier.weight(1f), shape=RoundedCornerShape(12.dp), colors=ButtonDefaults.buttonColors(containerColor=if(tab==key) Color(0xFF3949AB) else Color.Transparent, contentColor=if(tab==key) Color.White else Color(0xFF3949AB))) { Text(label) }
                        }
                    }
                    if (tab == "login") {
                        Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                                OutlinedTextField(value = baseUrl, onValueChange = onBaseUrl, label = { Text("Project Manager API URL") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = loginEmail, onValueChange = onLoginEmail, label = { Text("Email address") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                                OutlinedTextField(value = loginPassword, onValueChange = onLoginPassword, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(14.dp))
                                Button(onClick=onLogin, enabled=!busy&&loginEmail.isNotBlank()&&loginPassword.isNotBlank(), modifier=Modifier.fillMaxWidth().height(52.dp), shape=RoundedCornerShape(16.dp)) { Text(if(busy) "Signing in…" else "Sign in") }
                        }
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                                OutlinedTextField(value = registerName, onValueChange = onRegisterName, label = { Text("Full name") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = registerWorkspace, onValueChange = onRegisterWorkspace, label = { Text("Workspace name") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = registerEmail, onValueChange = onRegisterEmail, label = { Text("Email address") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                                OutlinedTextField(value = registerPassword, onValueChange = onRegisterPassword, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = registerConfirm, onValueChange = onRegisterConfirm, label = { Text("Confirm password") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(14.dp))
                                Row(Modifier.fillMaxWidth().clickable(enabled=!busy){policyAccepted=!policyAccepted}, verticalAlignment=Alignment.CenterVertically) {
                                    Checkbox(checked=policyAccepted, onCheckedChange={policyAccepted=it}, enabled=!busy)
                                    Text("I agree to the Terms of Service and Privacy Policy", color=Color(0xFF3949AB))
                                }
                                Button(onClick=onRegister, enabled=!busy&&policyAccepted, modifier=Modifier.fillMaxWidth().height(52.dp), shape=RoundedCornerShape(16.dp)) { Text(if(busy) "Submitting request…" else "Request account") }
                                if(!policyAccepted) Text("Please accept the Terms of Service and Privacy Policy to continue.", color=Color(0xFFC62828), style=MaterialTheme.typography.bodySmall)
                        }
                    }
                    if(error!=null) Text(error,color=if(tab=="register" && error.contains("submitted",true)) Color(0xFF2E7D32) else MaterialTheme.colorScheme.error,textAlign=TextAlign.Center,modifier=Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
private fun Dashboard(
    projects: List<Project>,
    selected: Project?,
    tasks: List<Task>,
    taskTitle: String,
    onTaskTitle: (String) -> Unit,
    taskContext: String,
    onTaskContext: (String) -> Unit,
    onSelect: (Project) -> Unit,
    onCreate: () -> Unit,
    onGoAhead: () -> Unit,
    onLogout: () -> Unit,
    onRefresh: () -> Unit,
    busy: Boolean,
    error: String?,
    onCreateProject: (String, String, String, String) -> Unit,
    onEditProject: (Project) -> Unit,
    onUpdateProject: (Project, String, String, String) -> Unit,
    showProjectForm: Boolean,
    onShowProjectForm: () -> Unit,
    onDismissProjectForm: () -> Unit,
    editingProject: Project?,
    onDismissEdit: () -> Unit,
    projectId: String,
    onProjectId: (String) -> Unit,
    projectName: String,
    onProjectName: (String) -> Unit,
    projectRepo: String,
    onProjectRepo: (String) -> Unit,
    projectDescription: String,
    onProjectDescription: (String) -> Unit
) {
    if (editingProject != null) {
        AlertDialog(
            onDismissRequest = onDismissEdit,
            title = { Text("Edit Project") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("ID: ${editingProject.id}")
                    OutlinedTextField(
                        projectName, onProjectName,
                        label = { Text("Project name") },
                        singleLine = true
                    )
                    OutlinedTextField(
                        projectRepo, onProjectRepo,
                        label = { Text("GitHub repository") },
                        singleLine = true
                    )
                    OutlinedTextField(
                        projectDescription, onProjectDescription,
                        label = { Text("Description") },
                        minLines = 3
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        onUpdateProject(
                            editingProject,
                            projectName,
                            projectRepo,
                            projectDescription
                        )
                    },
                    enabled = !busy && projectName.isNotBlank()
                ) {
                    Text("Save")
                }
            },
            dismissButton = { TextButton(onClick = onDismissEdit) { Text("Cancel") } }
        )
    }

    if (showProjectForm) {
        AlertDialog(
            onDismissRequest = onDismissProjectForm,
            title = { Text("Create RSS Project") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(projectId, onProjectId, label = { Text("Project ID") }, singleLine = true)
                    OutlinedTextField(projectName, onProjectName, label = { Text("Project name") }, singleLine = true)
                    OutlinedTextField(projectRepo, onProjectRepo, label = { Text("GitHub repository") }, singleLine = true)
                    OutlinedTextField(projectDescription, onProjectDescription, label = { Text("Description") }, minLines = 3)
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        onCreateProject(
                            projectId,
                            projectName,
                            projectRepo,
                            projectDescription
                        )
                    },
                    enabled = !busy && projectId.isNotBlank() && projectName.isNotBlank()
                ) {
                    Text("Create")
                }
            },
            dismissButton = { TextButton(onClick = onDismissProjectForm) { Text("Cancel") } }        )
    }

    LazyColumn(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AsyncImage(
                        model = "https://raw.githubusercontent.com/riyazamra1/RSS-AI-Project-Manager/main/web/assets/rss-ai-project-manager-logo.png",
                        contentDescription = "RSS AI Project Manager logo",
                        modifier = Modifier.size(56.dp), contentScale = ContentScale.Fit
                    )
                    Spacer(Modifier.width(10.dp))
                    Text("RSS Projects", style = MaterialTheme.typography.headlineSmall)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onRefresh, enabled = !busy) { Text("Refresh") }
                    OutlinedButton(onClick = onLogout, enabled = !busy) { Text("Logout") }
                    Button(onClick = onShowProjectForm, enabled = !busy) { Text("New") }
                }
            }
        }

        items(projects) { project ->
            ElevatedCard(
                onClick = { onSelect(project) },
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(Modifier.padding(16.dp)) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(project.name, style = MaterialTheme.typography.titleMedium)
                            Text(project.repository ?: "Repository not configured")
                            Text("Status: ${project.status ?: "unknown"}")
                        }
                        TextButton(onClick = { onEditProject(project) }, enabled = !busy) {
                            Text("Edit")
                        }
                    }
                    if (!project.description.isNullOrBlank()) {
                        Text(
                            project.description,
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }

        if (selected != null) {
            item {
                HorizontalDivider()
                Text("Selected: ${selected.name}", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    taskTitle,
                    onTaskTitle,
                    label = { Text("Task / next action") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    taskContext,
                    onTaskContext,
                    label = { Text("Context / requirements") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = onCreate,
                        enabled = !busy && taskTitle.isNotBlank()
                    ) { Text("Create Task") }
                    Button(
                        onClick = onGoAhead,
                        enabled = !busy
                    ) { Text(if (busy) "Working..." else "Go Ahead") }
                }
                Spacer(Modifier.height(8.dp))
                Text("Tasks", style = MaterialTheme.typography.titleMedium)
            }

            items(tasks) { task ->
                ListItem(
                    headlineContent = { Text(task.title) },
                    supportingContent = { Text("Status: ${task.status}") }
                )
            }
        }

        if (error != null) {
            item {
                Text(
                    error,
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}