package com.riyaz.rssaiprojectmanager

import android.os.Bundle
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.Settings
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
    private val client = OkHttpClient.Builder().connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS).readTimeout(30, java.util.concurrent.TimeUnit.SECONDS).writeTimeout(30, java.util.concurrent.TimeUnit.SECONDS).callTimeout(45, java.util.concurrent.TimeUnit.SECONDS).build()
    var token: String? = null
    var workspaceId: String? = null

    private fun request(path: String, method: String, body: String? = null): String {
        val target = Uri.parse(baseUrl.trimEnd('/') + path)
        require(target.scheme == "https" && !target.host.isNullOrBlank() && target.host == Uri.parse(baseUrl).host && target.userInfo == null) {
            "For security, enter a valid HTTPS API URL. Insecure destinations are blocked."
        }
        val builder = Request.Builder()
            .url(target.toString())
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

    fun importRegistryProjects(): JSONObject = JSONObject(request("/api/v1/projects/import-registry", "POST", "{}"))

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

private data class AppUpdate(
    val versionCode: Long,
    val versionName: String,
    val apkUrl: String,
    val sha256: String?,
    val releaseNotes: String
)

private object AppUpdater {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .callTimeout(90, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    fun checkForUpdate(currentVersionCode: Long): AppUpdate? {
        val request = Request.Builder()
            .url("https://api.github.com/repos/riyazamra1/RSS-AI-Project-Manager/releases/latest")
            .header("Accept", "application/vnd.github+json")
            .header("User-Agent", "RSS-AI-Project-Manager-Updater")
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) error("Update check failed (HTTP ${response.code}).")
            val release = JSONObject(response.body?.string().orEmpty())
            val tag = release.optString("tag_name")
            val version = tag.substringAfterLast('v').toLongOrNull()
                ?: release.optLong("version_code", 0L)
            if (version <= currentVersionCode) return null
            val assets = release.optJSONArray("assets") ?: JSONArray()
            var apkUrl: String? = null
            var apkDigest: String? = null
            for (i in 0 until assets.length()) {
                val asset = assets.optJSONObject(i) ?: continue
                if (asset.optString("name") == "app-debug.apk") {
                    apkUrl = asset.optString("browser_download_url")
                    apkDigest = asset.optString("digest").removePrefix("sha256:").takeIf { it.matches(Regex("(?i)[0-9a-f]{64}")) }
                    break
                }
            }
            val url = apkUrl ?: error("The latest release has no installable APK yet.")
            if (Uri.parse(url).scheme != "https" || Uri.parse(url).host != "github.com") {
                error("The release contains an untrusted APK download URL.")
            }
            return AppUpdate(
                versionCode = version,
                versionName = release.optString("name").ifBlank { tag },
                apkUrl = url,
                sha256 = apkDigest,
                releaseNotes = release.optString("body").take(1200)
            )
        }
    }

    fun downloadAndInstall(context: Context, url: String, expectedSha256: String?) {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O &&
            !context.packageManager.canRequestPackageInstalls()
        ) {
            val settingsIntent = Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}")
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(settingsIntent)
            error("Allow RSS AI Project Manager to install updates, return to the app, then tap Download & install again.")
        }
        val host = Uri.parse(url).host.orEmpty()
        if (!(host == "github.com" || host.endsWith(".githubusercontent.com"))) {
            error("The update download URL is not trusted.")
        }
        val folder = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir
        if (!folder.exists() && !folder.mkdirs()) error("Could not create the update download folder.")
        val apk = File(folder, "rss-ai-project-manager-update.apk")
        val request = Request.Builder().url(url).header("User-Agent", "RSS-AI-Project-Manager-Updater").build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) error("APK download failed (HTTP ${response.code}).")
            val body = response.body ?: error("The APK download was empty.")
            body.byteStream().use { input ->
                FileOutputStream(apk).use { output -> input.copyTo(output) }
            }
        }
        if (!apk.isFile || apk.length() < 1_000_000L) {
            apk.delete()
            error("The downloaded APK is incomplete. Please try again.")
        }
        if (!expectedSha256.isNullOrBlank()) {
            val actual = java.security.MessageDigest.getInstance("SHA-256")
                .digest(apk.readBytes()).joinToString("") { "%02x".format(it) }
            if (!actual.equals(expectedSha256, ignoreCase = true)) {
                apk.delete()
                error("APK integrity verification failed. The update was rejected.")
            }
        }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", apk)
        val installIntent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(installIntent)
    }
}

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
    var success by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var availableUpdate by remember { mutableStateOf<AppUpdate?>(null) }
    var updateMessage by remember { mutableStateOf<String?>(null) }
    var checkingUpdates by remember { mutableStateOf(false) }
    var installingUpdate by remember { mutableStateOf(false) }
    var autoUpdateEnabled by remember { mutableStateOf(securePrefs.getBoolean("auto_update_enabled", true)) }
    var themeChoice by remember { mutableStateOf(securePrefs.getString("theme_choice", "Royal") ?: "Royal") }

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

    fun checkForUpdates(showResultWhenCurrent: Boolean = false) {
        if (checkingUpdates) return
        checkingUpdates = true
        scope.launch(Dispatchers.IO) {
            try {
                val packageInfo = context.packageManager.getPackageInfo(context.packageName, 0)
                val installedCode = androidx.core.content.pm.PackageInfoCompat.getLongVersionCode(packageInfo)
                val update = AppUpdater.checkForUpdate(installedCode)
                securePrefs.edit().putLong("last_update_check", System.currentTimeMillis()).apply()
                if (update != null) {
                    availableUpdate = update
                    updateMessage = null
                } else if (showResultWhenCurrent) {
                    availableUpdate = null
                    updateMessage = "You're using the latest version."
                } else {
                    availableUpdate = null
                }
            } catch (e: Exception) {
                if (showResultWhenCurrent) {
                    updateMessage = e.message ?: "Could not check for updates. Please try again."
                }
            } finally {
                checkingUpdates = false
            }
        }
    }

    fun loadProjects() {
        scope.launch(Dispatchers.IO) {
            try {
                var json = api.projects()
                if (json.length() == 0) {
                    api.importRegistryProjects()
                    json = api.projects()
                }
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
    LaunchedEffect(autoUpdateEnabled) {
        val lastCheck = securePrefs.getLong("last_update_check", 0L)
        val dayMillis = 24L * 60L * 60L * 1000L
        if (autoUpdateEnabled && System.currentTimeMillis() - lastCheck >= dayMillis) {
            checkForUpdates(showResultWhenCurrent = false)
        }
    }

    MaterialTheme {
        Surface(Modifier.fillMaxSize()) {
            if (!introSeen) {
                IntroFlowScreen(themeChoice = themeChoice, onFinish = {
                    introSeen = true
                    securePrefs.edit().putBoolean("intro_seen", true).apply()
                })
            } else if (!signedIn) {
                AuthScreen(
                    themeChoice = themeChoice,
                    tab = authTab,
                    onTab = { authTab = it; error = null; success = null },
                    baseUrl = baseUrl, onBaseUrl = { baseUrl = it },
                    loginEmail = email, onLoginEmail = { email = it },
                    loginPassword = password, onLoginPassword = { password = it },
                    registerName = registerName, onRegisterName = { registerName = it },
                    registerEmail = registerEmail, onRegisterEmail = { registerEmail = it },
                    registerPassword = registerPassword, onRegisterPassword = { registerPassword = it },
                    registerConfirm = registerConfirm, onRegisterConfirm = { registerConfirm = it },
                    registerWorkspace = registerWorkspace, onRegisterWorkspace = { registerWorkspace = it },
                    error = error, success = success, busy = busy,
                    onLogin = {
                        if (email.isBlank() || password.isBlank()) { error = "Enter email and password."; return@AuthScreen }
                        error = null; success = null
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
                                error = null
                                success = null
                                busy = true
                                scope.launch(Dispatchers.IO) {
                                    try {
                                        val result = api.register(name, mail, registerPassword, workspace)
                                        success = result.optString("message", "Account request submitted. Check your email and wait for administrator approval.").ifBlank { "Account request submitted. Check your email and wait for administrator approval." }
                                        email = mail; password = ""; registerPassword = ""; registerConfirm = ""
                                    } catch (e: Exception) {
                                        error = e.message ?: "Registration failed. Please try again."
                                    } finally { busy = false }
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
                    onCheckUpdates = { checkForUpdates(showResultWhenCurrent = true) },
                    checkingUpdates = checkingUpdates,
                    onOpenUpdates = { availableUpdate = null; updateMessage = "Check for updates using the Updates button above." },
                    autoUpdateEnabled = autoUpdateEnabled,
                    onAutoUpdateEnabled = { enabled ->
                        autoUpdateEnabled = enabled
                        securePrefs.edit().putBoolean("auto_update_enabled", enabled).apply()
                    },
                    themeChoice = themeChoice,
                    onThemeChoice = { choice ->
                        themeChoice = choice
                        securePrefs.edit().putString("theme_choice", choice).apply()
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
            if (availableUpdate != null || updateMessage != null) {
                val update = availableUpdate
                AlertDialog(
                    onDismissRequest = { availableUpdate = null; updateMessage = null },
                    icon = { Text("⬆", color = Color(0xFF4B3CC4), style = MaterialTheme.typography.headlineMedium) },
                    title = { Text(if (update != null) "RSS AI Project Manager update" else "App updates") },
                    text = {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (update != null) {
                                Text("Version ${update.versionName} is available.")
                                if (update.releaseNotes.isNotBlank()) Text(update.releaseNotes)
                            } else {
                                Text(updateMessage.orEmpty())
                            }
                            if (updateMessage != null && update != null) {
                                Text(updateMessage.orEmpty(), color = MaterialTheme.colorScheme.error)
                            }
                            if (checkingUpdates) CircularProgressIndicator()
                        }
                    },
                    confirmButton = {
                        if (update != null) {
                            Button(
                                enabled = !installingUpdate,
                                onClick = {
                                    installingUpdate = true
                                    updateMessage = null
                                    scope.launch(Dispatchers.IO) {
                                        try {
                                            AppUpdater.downloadAndInstall(context, update.apkUrl, update.sha256)
                                            updateMessage = "Opening Android's installer…"
                                        } catch (e: Exception) {
                                            updateMessage = e.message ?: "Could not install the update."
                                        } finally {
                                            installingUpdate = false
                                        }
                                    }
                                }
                            ) { Text(if (installingUpdate) "Preparing update…" else "Download & install") }
                        } else {
                            TextButton(onClick = { updateMessage = null }) { Text("Close") }
                        }
                    },
                    dismissButton = {
                        if (update != null) {
                            TextButton(onClick = { availableUpdate = null; updateMessage = null }) { Text("Later") }
                        }
                    }
                )
            }
        }
    }
}

@Composable
private fun AnimatedRoyalBackground(themeChoice: String = "Royal", content: @Composable BoxScope.() -> Unit) {
    val transition = rememberInfiniteTransition(label = "rssRoyal")
    val shift by transition.animateFloat(-900f, 1800f, infiniteRepeatable(tween(9000, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "shift")
    val palette = when (themeChoice) {
        "Ocean" -> listOf(Color(0xFF003B73), Color(0xFF0077B6), Color(0xFF48CAE4), Color(0xFF90E0EF), Color(0xFFCAF0F8))
        "Emerald" -> listOf(Color(0xFF064E3B), Color(0xFF059669), Color(0xFF34D399), Color(0xFFA7F3D0), Color(0xFFECFDF5))
        "Violet" -> listOf(Color(0xFF4C1D95), Color(0xFF7C3AED), Color(0xFFA78BFA), Color(0xFFDDD6FE), Color(0xFFF5F3FF))
        else -> listOf(Color(0xFF283593), Color(0xFF7E57C2), Color(0xFF00ACC1), Color(0xFF26A69A), Color(0xFFE0F7FA))
    }
    val gradient = Brush.linearGradient(palette, Offset(0f, shift), Offset(1200f, shift + 1200f))
    Box(Modifier.fillMaxSize().background(gradient), content = content)
}

@Composable
private fun IntroFlowScreen(themeChoice: String, onFinish: () -> Unit) {
    var page by remember { mutableStateOf(0) }
    val titles = listOf("Manage Every RSS Project", "Turn Requirements Into Tasks", "Let AI Execute", "Track Progress Clearly")
    val bodies = listOf("One command center for your RSS project portfolio.", "Capture requirements, priorities and next actions in one place.", "Connect RSS Core and automation so approved work can move forward.", "Monitor projects, tasks and execution status from your dashboard.")
    AnimatedRoyalBackground(themeChoice) {
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
    themeChoice: String,
    tab: String, onTab: (String) -> Unit,
    baseUrl: String, onBaseUrl: (String) -> Unit,
    loginEmail: String, onLoginEmail: (String) -> Unit,
    loginPassword: String, onLoginPassword: (String) -> Unit,
    registerName: String, onRegisterName: (String) -> Unit,
    registerEmail: String, onRegisterEmail: (String) -> Unit,
    registerPassword: String, onRegisterPassword: (String) -> Unit,
    registerConfirm: String, onRegisterConfirm: (String) -> Unit,
    registerWorkspace: String, onRegisterWorkspace: (String) -> Unit,
    error: String?, success: String?, busy: Boolean, onLogin: () -> Unit, onRegister: () -> Unit
) {
    var policyAccepted by remember { mutableStateOf(false) }
    AnimatedRoyalBackground(themeChoice) {
        Box(Modifier.fillMaxSize().imePadding().navigationBarsPadding()) {
            Column(
                Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 20.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Spacer(Modifier.height(12.dp))
                Image(painter = painterResource(R.drawable.rss_ai_project_manager_logo), contentDescription = "RSS AI Project Manager logo", modifier = Modifier.size(width = 140.dp, height = 82.dp), contentScale = ContentScale.Fit)
                Text("RSS AI PROJECT MANAGER", color = Color.White, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(12.dp))
                Card(Modifier.fillMaxWidth().widthIn(max = 520.dp), shape = RoundedCornerShape(28.dp), colors = CardDefaults.cardColors(Color.White.copy(alpha = .97f)), elevation = CardDefaults.cardElevation(10.dp)) {
                    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
                        Text("Welcome to RSS AI Project Manager", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Color(0xFF182052), textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                        success?.let { Text(it, color = Color(0xFF137333), fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()) }
                        Row(Modifier.fillMaxWidth().background(Color(0xFFE8EAF6), RoundedCornerShape(16.dp)).padding(4.dp)) {
                            listOf("login" to "Sign In", "register" to "Create Account").forEach { (key, label) ->
                                Button(onClick = { onTab(key) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(12.dp), colors = ButtonDefaults.buttonColors(containerColor = if (tab == key) Color(0xFF3949AB) else Color.Transparent, contentColor = if (tab == key) Color.White else Color(0xFF3949AB))) { Text(label) }
                            }
                        }
                        if (tab == "login") {
                            Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                                OutlinedTextField(value = baseUrl, onValueChange = onBaseUrl, label = { Text("Project Manager API URL") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = loginEmail, onValueChange = onLoginEmail, label = { Text("Email address") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                                OutlinedTextField(value = loginPassword, onValueChange = onLoginPassword, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(14.dp))
                                Button(onClick = onLogin, enabled = !busy && loginEmail.isNotBlank() && loginPassword.isNotBlank(), modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(16.dp)) { Text(if (busy) "Signing in…" else "Sign in") }
                                error?.let { Text(it, color = Color(0xFFC62828), textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()) }
                            }
                        } else {
                            Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                                OutlinedTextField(value = registerName, onValueChange = onRegisterName, label = { Text("Full name") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = registerWorkspace, onValueChange = onRegisterWorkspace, label = { Text("Workspace name") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = registerEmail, onValueChange = onRegisterEmail, label = { Text("Email address") }, modifier = Modifier.fillMaxWidth(), singleLine = true, shape = RoundedCornerShape(14.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                                OutlinedTextField(value = registerPassword, onValueChange = onRegisterPassword, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(14.dp))
                                OutlinedTextField(value = registerConfirm, onValueChange = onRegisterConfirm, label = { Text("Confirm password") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(14.dp))
                                Row(Modifier.fillMaxWidth().clickable(enabled = !busy) { policyAccepted = !policyAccepted }, verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(checked = policyAccepted, onCheckedChange = { policyAccepted = it }, enabled = !busy)
                                    Text("I agree to the Terms of Service and Privacy Policy", color = Color(0xFF3949AB))
                                }
                                if (!policyAccepted) Text("Please accept the Terms of Service and Privacy Policy to continue.", color = Color(0xFFC62828), style = MaterialTheme.typography.bodySmall)
                                Button(onClick = onRegister, enabled = !busy && policyAccepted, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(16.dp)) { Text(if (busy) "Submitting request…" else "Request account") }
                                error?.let {
                                    Surface(Modifier.fillMaxWidth(), color = Color(0xFFFFEBEE), shape = RoundedCornerShape(12.dp)) {
                                        Text(it, color = Color(0xFFC62828), textAlign = TextAlign.Center, modifier = Modifier.padding(10.dp))
                                    }
                                }
                            }
                        }
                    }
                }
                Spacer(Modifier.height(20.dp))
            }

        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
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
    onCheckUpdates: () -> Unit,
    checkingUpdates: Boolean,
    onOpenUpdates: () -> Unit,
    autoUpdateEnabled: Boolean,
    onAutoUpdateEnabled: (Boolean) -> Unit,
    themeChoice: String,
    onThemeChoice: (String) -> Unit,
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
    var page by remember { mutableStateOf("Dashboard") }
    val themeAccent = when (themeChoice) {
        "Ocean" -> Color(0xFF0077B6)
        "Emerald" -> Color(0xFF059669)
        "Violet" -> Color(0xFF7C3AED)
        else -> Color(0xFF4B3CC4)
    }

    if (editingProject != null) {
        AlertDialog(
            onDismissRequest = onDismissEdit,
            title = { Text("Edit Project") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("ID: ${editingProject.id}")
                    OutlinedTextField(projectName, onProjectName, label = { Text("Project name") }, singleLine = true)
                    OutlinedTextField(projectRepo, onProjectRepo, label = { Text("GitHub repository") }, singleLine = true)
                    OutlinedTextField(projectDescription, onProjectDescription, label = { Text("Description") }, minLines = 3)
                }
            },
            confirmButton = {
                Button(onClick = { onUpdateProject(editingProject, projectName, projectRepo, projectDescription) }, enabled = !busy && projectName.isNotBlank()) { Text("Save") }
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
                Button(onClick = { onCreateProject(projectId, projectName, projectRepo, projectDescription) }, enabled = !busy && projectId.isNotBlank() && projectName.isNotBlank()) { Text("Create") }
            },
            dismissButton = { TextButton(onClick = onDismissProjectForm) { Text("Cancel") } }
        )
    }

    Scaffold(
        containerColor = when (themeChoice) { "Ocean" -> Color(0xFFF1FAFF); "Emerald" -> Color(0xFFF1FCF6); "Violet" -> Color(0xFFF8F5FF); else -> Color(0xFFF7F8FF) },
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("RSS AI Project Manager", fontWeight = FontWeight.Bold)
                        Text(page, style = MaterialTheme.typography.labelMedium, color = Color(0xFF68738D))
                    }
                },
                actions = {
                    TextButton(onClick = onCheckUpdates, enabled = !checkingUpdates) { Text(if (checkingUpdates) "Checking…" else "Updates") }
                    IconButton(onClick = onRefresh, enabled = !busy) { Text("↻", fontSize = MaterialTheme.typography.titleLarge.fontSize) }
                    TextButton(onClick = onLogout, enabled = !busy) { Text("Logout") }
                }
            )
        }
    ) { padding ->
        Row(Modifier.fillMaxSize().padding(padding)) {
            NavigationRail(containerColor = themeAccent.copy(alpha = .96f)) {
                listOf("Dashboard", "Projects", "Tasks", "Settings", "Premium").forEach { item ->
                    NavigationRailItem(
                        selected = page == item,
                        onClick = { page = item },
                        icon = { Text(when (item) { "Dashboard" -> "⌂"; "Projects" -> "▦"; "Tasks" -> "✓"; "Settings" -> "⚙"; else -> "✦" }, color = if (page == item) Color(0xFF20265C) else Color.White) },
                        label = { Text(item, color = Color.White) },
                        colors = NavigationRailItemDefaults.colors(
                            selectedIconColor = Color(0xFF20265C),
                            selectedTextColor = Color.White,
                            indicatorColor = Color.White.copy(alpha = .96f)
                        )
                    )
                }
            }

            LazyColumn(
                Modifier.fillMaxSize().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                if (page == "Dashboard") {
                    item {
                        Card(
                            Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(22.dp),
                            colors = CardDefaults.cardColors(
                                containerColor = Color(0xFF4B3CC4)
                            )
                        ) {
                            Column(Modifier.padding(20.dp)) {
                                Text("Welcome to your project control center", color = Color.White, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                                Spacer(Modifier.height(6.dp))
                                Text("Manage projects, requirements, tasks and approved execution from one place.", color = Color.White.copy(alpha = .9f))
                                Spacer(Modifier.height(14.dp))
                                Button(onClick = onShowProjectForm, enabled = !busy, colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color(0xFF4B3CC4))) {
                                    Text("Create Project")
                                }
                            }
                        }
                    }
                    item {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            MetricCard("Projects", projects.size.toString(), Modifier.weight(1f))
                            MetricCard("Tasks", tasks.size.toString(), Modifier.weight(1f))
                            MetricCard("Active", tasks.count { it.status.lowercase() in listOf("running", "in_progress", "dispatched") }.toString(), Modifier.weight(1f))
                        }
                    }
                    item {
                        SectionCard("Projects") {
                            if (projects.isEmpty()) {
                                EmptyState("No projects yet", "Create your first RSS project to start managing requirements and tasks.", "Create Project", onShowProjectForm)
                            } else {
                                projects.take(5).forEach { project ->
                                    ProjectRow(project, selected?.id == project.id, onSelect, onEditProject, busy)
                                }
                            }
                        }
                    }
                    item {
                        SectionCard("Execution") {
                            Text("RSS Core → RAY is the approved execution path. Project Manager creates and tracks work; execution stays server-side.", color = Color(0xFF68738D))
                            Spacer(Modifier.height(10.dp))
                            Button(onClick = onGoAhead, enabled = !busy) { Text(if (busy) "Working…" else "Go Ahead") }
                            if (!error.isNullOrBlank()) {
                                Spacer(Modifier.height(10.dp))
                                Text(error, color = MaterialTheme.colorScheme.error)
                            }
                        }
                    }
                } else if (page == "Projects") {
                    item {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Text("Projects", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                            Button(onClick = onShowProjectForm, enabled = !busy) { Text("New Project") }
                        }
                    }
                    if (projects.isEmpty()) {
                        item { EmptyState("No projects found", "Your workspace currently has no project records.", "Create Project", onShowProjectForm) }
                    } else {
                        items(projects) { project ->
                            ProjectRow(project, selected?.id == project.id, onSelect, onEditProject, busy)
                        }
                    }
                } else if (page == "Settings") {
                    item {
                        Text("Settings & Security", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        Text("Your preferences are stored on this device.", color = Color(0xFF68738D))
                    }
                    item {
                        SectionCard("Automatic updates") {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text("Check for updates automatically", fontWeight = FontWeight.SemiBold)
                                    Text("Checks once per day when the app opens. Android still asks before installing an APK.", color = Color(0xFF68738D))
                                }
                                Switch(checked = autoUpdateEnabled, onCheckedChange = onAutoUpdateEnabled)
                            }
                            OutlinedButton(onClick = onCheckUpdates, enabled = !checkingUpdates, modifier = Modifier.fillMaxWidth()) {
                                Text(if (checkingUpdates) "Checking for updates…" else "Check now")
                            }
                        }
                    }
                    item {
                        SectionCard("Appearance") {
                            Text("Choose your app accent style", color = Color(0xFF68738D))
                            listOf("Royal", "Ocean", "Emerald", "Violet").forEach { choice ->
                                Row(Modifier.fillMaxWidth().clickable { onThemeChoice(choice) }.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                                    RadioButton(selected = themeChoice == choice, onClick = { onThemeChoice(choice) })
                                    Text(choice)
                                }
                            }
                            Text("Preference saved. Full component-level theme customization can be enabled in a future theme-studio release.", color = Color(0xFF68738D), style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    item {
                        SectionCard("Security") {
                            Text("Session tokens are stored with Android encrypted preferences.", color = Color(0xFF68738D))
                            Text("API requests require HTTPS and block insecure endpoints.", color = Color(0xFF68738D))
                            Text("Update APK integrity is checked against the release digest when GitHub provides one.", color = Color(0xFF68738D))
                            OutlinedButton(onClick = onLogout, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Sign out and clear session") }
                        }
                    }
                    item {
                        SectionCard("App information") {
                            Text("Package: ${androidx.compose.ui.platform.LocalContext.current.packageName}", color = Color(0xFF68738D))
                            Text("Installed version: ${androidx.compose.ui.platform.LocalContext.current.packageManager.getPackageInfo(androidx.compose.ui.platform.LocalContext.current.packageName, 0).versionName}", color = Color(0xFF68738D))
                        }
                    }
                } else if (page == "Premium") {
                    item {
                        Text("RSS Premium", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        Text("Premium access is controlled by the RSS account and licensing service.", color = Color(0xFF68738D))
                    }
                    item {
                        SectionCard("Premium capabilities") {
                            listOf("Advanced AI automation and task orchestration", "Portfolio-wide analytics and reports", "Extended project and workspace controls", "Priority automation and integrations", "Advanced security and audit controls").forEach { feature ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text("✦", color = Color(0xFF6A50E9))
                                    Spacer(Modifier.width(8.dp))
                                    Text(feature)
                                }
                            }
                            Text("Plan and payment controls appear when the RSS licensing endpoint is configured. This screen does not claim a paid plan is active.", color = Color(0xFF68738D), style = MaterialTheme.typography.bodySmall)
                        }
                    }
                } else {
                    item {
                        Text("Tasks", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        if (selected != null) Text("Project: ${selected.name}", color = Color(0xFF68738D))
                    }
                    if (selected == null) {
                        item { EmptyState("Select a project", "Choose a project from the Projects section to view and create tasks.", "View Projects") { page = "Projects" } }
                    } else {
                        item {
                            SectionCard("Create Task") {
                                OutlinedTextField(taskTitle, onTaskTitle, label = { Text("Task / next action") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                                Spacer(Modifier.height(8.dp))
                                OutlinedTextField(taskContext, onTaskContext, label = { Text("Context / requirements") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                                Spacer(Modifier.height(8.dp))
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(onClick = onCreate, enabled = !busy && taskTitle.isNotBlank()) { Text("Create Task") }
                                    OutlinedButton(onClick = onGoAhead, enabled = !busy) { Text("Go Ahead") }
                                }
                            }
                        }
                        if (tasks.isEmpty()) {
                            item { EmptyState("No tasks yet", "Create a task for this project to begin tracking work.", "Focus task field") { } }
                        } else {
                            items(tasks) { task ->
                                Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) {
                                    Column(Modifier.padding(16.dp)) {
                                        Text(task.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                        Spacer(Modifier.height(5.dp))
                                        Text("Status: ${task.status}", color = Color(0xFF68738D))
                                    }
                                }
                            }
                        }
                    }
                    if (!error.isNullOrBlank()) item { Text(error, color = MaterialTheme.colorScheme.error) }
                }
            }
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier, shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(14.dp)) {
            Text(label, color = Color(0xFF68738D), style = MaterialTheme.typography.labelMedium)
            Text(value, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = Color(0xFF20265C))
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun EmptyState(title: String, message: String, action: String, onAction: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("◈", fontSize = MaterialTheme.typography.displaySmall.fontSize, color = Color(0xFF6A50E9))
        Spacer(Modifier.height(8.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        Text(message, color = Color(0xFF68738D), textAlign = TextAlign.Center)
        Spacer(Modifier.height(10.dp))
        OutlinedButton(onClick = onAction) { Text(action) }
    }
}

@Composable
private fun ProjectRow(project: Project, selected: Boolean, onSelect: (Project) -> Unit, onEdit: (Project) -> Unit, busy: Boolean) {
    Card(
        onClick = { onSelect(project) },
        Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = if (selected) Color(0xFFECE9FF) else Color.White)
    ) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(project.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text(project.repository ?: "Repository not configured", color = Color(0xFF68738D), maxLines = 1)
                Text("Status: ${project.status ?: "unknown"}", color = Color(0xFF68738D), style = MaterialTheme.typography.labelSmall)
            }
            TextButton(onClick = { onEdit(project) }, enabled = !busy) { Text("Edit") }
        }
    }
}

