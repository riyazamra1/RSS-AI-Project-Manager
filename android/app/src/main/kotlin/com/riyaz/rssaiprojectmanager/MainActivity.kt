package com.riyaz.rssaiprojectmanager

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
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
        val builder = Request.Builder().url(baseUrl.trimEnd('/') + path).addHeader("Accept", "application/json")
        token?.let { builder.addHeader("Authorization", "Bearer " + it) }
        workspaceId?.let { builder.addHeader("X-Workspace-ID", it) }
        if (body != null) builder.method(method, body.toRequestBody("application/json".toMediaType()))
        else builder.method(method, null)
        client.newCall(builder.build()).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) error("HTTP " + response.code + ": " + text.take(500))
            return text
        }
    }

    fun login(email: String, password: String): JSONObject =
        JSONObject(request("/auth/login", "POST", JSONObject().put("email", email).put("password", password).toString()))

    fun projects(): JSONArray = JSONArray(request("/api/v1/projects", "GET"))

    fun createProject(id: String, name: String, repository: String?, description: String): JSONObject {
        val body = JSONObject().put("id", id).put("name", name)
        if (!repository.isNullOrBlank()) body.put("repository", repository)
        if (description.isNotBlank()) body.put("description", description)
        return JSONObject(request("/api/v1/projects", "POST", body.toString()))
    }
    fun tasks(projectId: String): JSONArray = JSONArray(request("/api/v1/tasks?project_id=" + projectId, "GET"))

    fun createTask(title: String, projectId: String, context: String): JSONObject {
        val body = JSONObject().put("title", title).put("project_id", projectId)
        if (context.isNotBlank()) body.put("context", context)
        return JSONObject(request("/api/v1/tasks", "POST", body.toString()))
    }

    fun goAhead(): JSONObject = JSONObject(request("/api/v1/tasks/run-next-user", "POST"))
}

data class Project(val id: String, val name: String, val repository: String?, val status: String?)
data class Task(val id: String, val title: String, val status: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ProjectManagerApp() }
    }
}

@Composable
private fun ProjectManagerApp() {
    var baseUrl by remember { mutableStateOf("https://rsscore.cv") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var signedIn by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val api = remember(baseUrl) { ProjectManagerApi(baseUrl) }
    val scope = rememberCoroutineScope()
    var projects by remember { mutableStateOf(emptyList<Project>()) }
    var selected by remember { mutableStateOf<Project?>(null) }
    var tasks by remember { mutableStateOf(emptyList<Task>()) }
    var taskTitle by remember { mutableStateOf("") }
    var taskContext by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var showProjectForm by remember { mutableStateOf(false) }
    var projectId by remember { mutableStateOf("") }
    var projectName by remember { mutableStateOf("") }
    var projectRepo by remember { mutableStateOf("") }

    fun loadProjects() {
        scope.launch(Dispatchers.IO) {
            try {
                val json = api.projects()
                projects = (0 until json.length()).map { i ->
                    json.getJSONObject(i).let { Project(it.getString("id"), it.getString("name"), it.optString("repository").ifBlank { null }, it.optString("status").ifBlank { null }) }
                }
                error = null
            } catch (e: Exception) { error = e.message }
        }
    }

    fun loadTasks(project: Project) {
        scope.launch(Dispatchers.IO) {
            try {
                val json = api.tasks(project.id)
                tasks = (0 until json.length()).map { i ->
                    json.getJSONObject(i).let { Task(it.getLong("id").toString(), it.getString("title"), it.getString("status")) }
                }
                error = null
            } catch (e: Exception) { error = e.message }
        }
    }

    MaterialTheme {
        Surface(Modifier.fillMaxSize()) {
            if (!signedIn) {
                LoginScreen(baseUrl, { baseUrl = it }, email, { email = it }, password, { password = it }, error, busy) {
                    busy = true
                    scope.launch(Dispatchers.IO) {
                        try {
                            val result = api.login(email, password)
                            api.token = result.getString("access_token")
                            val workspace = result.optJSONObject("workspace")
                            if (workspace != null) api.workspaceId = workspace.getString("id")
                            else {
                                val workspaces = result.optJSONArray("workspaces")
                                if (workspaces != null && workspaces.length() > 0) api.workspaceId = workspaces.getJSONObject(0).getString("id")
                            }
                            if (api.workspaceId.isNullOrBlank()) error("No active workspace returned by server")
                            signedIn = true
                            loadProjects()
                            error = null
                        } catch (e: Exception) { error = e.message }
                        finally { busy = false }
                    }
                }
            } else {
                Dashboard(
                    projects, selected, tasks, taskTitle, { taskTitle = it }, taskContext, { taskContext = it },
                    onSelect = { selected = it; loadTasks(it) },
                    onCreate = {
                        val project = selected ?: return@Dashboard
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                api.createTask(taskTitle, project.id, taskContext)
                                taskTitle = ""; taskContext = ""
                                loadTasks(project)
                                error = null
                            } catch (e: Exception) { error = e.message }
                            finally { busy = false }
                        }
                    },
                    onGoAhead = {
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                val result = api.goAhead()
                                error = "Execution: " + result.optString("status") + "  Task: " + result.optString("task_id")
                                selected?.let { loadTasks(it) }
                            } catch (e: Exception) { error = e.message }
                            finally { busy = false }
                        }
                    },
                    onRefresh = { loadProjects(); selected?.let { loadTasks(it) } },
                    busy = busy,
                    error = error,
                    onCreateProject = { id, name, repo ->
                        busy = true
                        scope.launch(Dispatchers.IO) {
                            try {
                                api.createProject(id, name, repo, "")
                                showProjectForm = false
                                projectId = ""; projectName = ""; projectRepo = ""
                                loadProjects()
                                error = null
                            } catch (e: Exception) { error = e.message }
                            finally { busy = false }
                        }
                    },
                    showProjectForm = showProjectForm,
                    onDismissProjectForm = { showProjectForm = false },
                    projectId = projectId, onProjectId = { projectId = it },
                    projectName = projectName, onProjectName = { projectName = it },
                    projectRepo = projectRepo, onProjectRepo = { projectRepo = it }
                )
            }
        }
    }
}

@Composable
private fun LoginScreen(
    baseUrl: String, onBaseUrl: (String) -> Unit,
    email: String, onEmail: (String) -> Unit,
    password: String, onPassword: (String) -> Unit,
    error: String?, busy: Boolean, onLogin: () -> Unit
) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("RSS AI Project Manager", style = MaterialTheme.typography.headlineMedium)
        Text("Full Android control client", style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(20.dp))
        OutlinedTextField(baseUrl, onBaseUrl, label = { Text("Backend / RSS Core API URL") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(email, onEmail, label = { Text("Email") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(password, onPassword, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Spacer(Modifier.height(12.dp))
        Button(onClick = onLogin, enabled = !busy && email.isNotBlank() && password.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
            Text(if (busy) "Signing in..." else "Sign in")
        }
        if (error != null) Text(error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 10.dp))
    }
}

@Composable
private fun Dashboard(
    projects: List<Project>, selected: Project?, tasks: List<Task>,
    taskTitle: String, onTaskTitle: (String) -> Unit,
    taskContext: String, onTaskContext: (String) -> Unit,
    onSelect: (Project) -> Unit, onCreate: () -> Unit, onGoAhead: () -> Unit,
    onRefresh: () -> Unit, busy: Boolean, error: String?,
    onCreateProject: (String, String, String) -> Unit,
    showProjectForm: Boolean, onDismissProjectForm: () -> Unit,
    projectId: String, onProjectId: (String) -> Unit,
    projectName: String, onProjectName: (String) -> Unit,
    projectRepo: String, onProjectRepo: (String) -> Unit
) {
    if (showProjectForm) {
        AlertDialog(
            onDismissRequest = onDismissProjectForm,
            title = { Text("Create RSS Project") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(projectId, onProjectId, label = { Text("Project ID") }, singleLine = true)
                    OutlinedTextField(projectName, onProjectName, label = { Text("Project name") }, singleLine = true)
                    OutlinedTextField(projectRepo, onProjectRepo, label = { Text("GitHub repository") }, singleLine = true)
                }
            },
            confirmButton = { Button(onClick = { onCreateProject(projectId.trim(), projectName.trim(), projectRepo.trim()) }, enabled = projectId.isNotBlank() && projectName.isNotBlank() && !busy) { Text("Create") } },
            dismissButton = { TextButton(onClick = onDismissProjectForm) { Text("Cancel") } }
        )
    }
    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("RSS Projects", style = MaterialTheme.typography.headlineSmall)
                OutlinedButton(onClick = onRefresh, enabled = !busy) { Text("Refresh") }
            }
        }
        items(projects) { project ->
            ElevatedCard(onClick = { onSelect(project) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(project.name, style = MaterialTheme.typography.titleMedium)
                    Text(project.repository ?: "Repository not configured")
                    Text("Status: " + (project.status ?: "unknown"))
                }
            }
        }
        if (selected != null) item {
            HorizontalDivider()
            Text("Selected: " + selected.name, style = MaterialTheme.typography.titleLarge)
            OutlinedTextField(taskTitle, onTaskTitle, label = { Text("Task / next action") }, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(taskContext, onTaskContext, label = { Text("Context / requirements") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onCreate, enabled = !busy && taskTitle.isNotBlank()) { Text("Create Task") }
                Button(onClick = onGoAhead, enabled = !busy) { Text(if (busy) "Working..." else "Go Ahead") }
            }
            Text("Tasks", style = MaterialTheme.typography.titleMedium)
            tasks.forEach { task ->
                ListItem(headlineContent = { Text(task.title) }, supportingContent = { Text("Status: " + task.status) })
            }
        }
        if (error != null) item { Text(error, color = MaterialTheme.colorScheme.error) }
    }
}
