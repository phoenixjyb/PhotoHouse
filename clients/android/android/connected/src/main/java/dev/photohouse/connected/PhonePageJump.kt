package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

@Composable internal fun PhonePageJump(current: Int, pageSize: Int, total: Long, zh: Boolean, dismiss: () -> Unit, go: (Int) -> Unit) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val last = (if (total > 0) (total - 1) / pageSize.coerceAtLeast(1) + 1 else 1).coerceAtMost(100000).toInt()
    var input by remember(current, last) { mutableStateOf("") }
    val target = input.toIntOrNull()?.takeIf { it in 1..last }
    AlertDialog(onDismissRequest = dismiss, title = { Text(t("Go to page", "跳转页面")) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Choose a page from 1 to $last", "选择第 1 至 $last 页"))
            OutlinedTextField(input, { if (it.length <= 6 && it.all { char -> char in '0'..'9' }) input = it },
                label = { Text(t("Page", "页码")) }, singleLine = true,
                placeholder = { Text(current.toString()) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { target?.let(go) }),
                isError = input.isNotEmpty() && target == null, modifier = Modifier.fillMaxWidth().testTag("phone-page-input"))
        } },
        dismissButton = { TextButton(onClick = dismiss) { Text(t("Cancel", "取消")) } },
        confirmButton = { Button(onClick = { target?.let(go) }, enabled = target != null, modifier = Modifier.testTag("phone-page-go")) { Text(t("Go", "跳转")) } })
}
