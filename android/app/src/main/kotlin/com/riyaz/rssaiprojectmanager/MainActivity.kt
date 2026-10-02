package com.riyaz.rssaiprojectmanager

import android.os.Bundle
import android.content.Context
import androidx.activity.ComponentActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Alignment
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
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
    var baseUrl by remember { mutableStateOf("https://rsscore.cv") }    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var workspaceId by remember { mutableStateOf(securePrefs.getString("workspace_id", null)) }
    var signedIn by remember { mutableStateOf(securePrefs.getString("token", null) != null) }
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
            if (!signedIn) {
                LoginScreen(
                    baseUrl = baseUrl,
                    onBaseUrl = { baseUrl = it },
                    email = email,
                    onEmail = { email = it },
                    password = password,
                    onPassword = { password = it },
                    error = error,
                    busy = busy
                ) {
                    busy = true
                    scope.launch(Dispatchers.IO) {
                        try {
                            val result = api.login(email.trim(), password)
                            api.token = result.getString("access_token")
                            securePrefs.edit().putString("token", api.token).apply()

                            val workspace = result.optJSONObject("workspace")
                            if (workspace != null) {
                                api.workspaceId = workspace.getString("id")
                            } else {
                                val workspaces = result.optJSONArray("workspaces")
                                if (workspaces != null && workspaces.length() > 0) {
                                    api.workspaceId = workspaces.getJSONObject(0).getString("id")
                                }
                            }

                            if (api.workspaceId.isNullOrBlank()) {
                                error("No active workspace returned by server")
                            } else {
                                workspaceId = api.workspaceId
                                securePrefs.edit().putString("workspace_id", api.workspaceId).apply()
                                signedIn = true
                                error = null
                                loadProjects()
                            }
                        } catch (e: Exception) {
                            error = e.message
                        } finally {
                            busy = false
                        }
                    }
                }
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
private fun LoginScreen(
    baseUrl: String,
    onBaseUrl: (String) -> Unit,
    email: String,
    onEmail: (String) -> Unit,
    password: String,
    onPassword: (String) -> Unit,
    error: String?,
    busy: Boolean,
    onLogin: () -> Unit
) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        AsyncImage(
            model = "https://raw.githubusercontent.com/riyazamra1/RSS-AI-Project-Manager/main/web/assets/rss-ai-project-manager-logo.png",
            contentDescription = "RSS AI Project Manager logo",
            modifier = Modifier.fillMaxWidth().height(96.dp).padding(bottom = 16.dp)
        )
        Text("RSS AI Project Manager", style = MaterialTheme.typography.headlineMedium)
        Text("Android control client", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(20.dp))
        OutlinedTextField(
            baseUrl, onBaseUrl,
            label = { Text("RSS Core API URL") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        OutlinedTextField(
            email, onEmail,
            label = { Text("Email") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        OutlinedTextField(
            password, onPassword,
            label = { Text("Password") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onLogin,
            enabled = !busy && email.isNotBlank() && password.isNotBlank(),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (busy) "Signing in..." else "Sign in")
        }
        if (error != null) {
            Text(
                error,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(top = 10.dp)
            )
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
                        modifier = Modifier.size(44.dp)
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