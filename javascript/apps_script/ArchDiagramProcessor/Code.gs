/*******************************************************/
/************** Web Service Functions ******************/
/*******************************************************/

function doGet(e) {
  if (e.parameter.fileId != null) {
    exportFileImagesToBucket(e.parameter.fileId)
    return HtmlService.createHtmlOutput('<b>Success!</b>');
  }
}

/*******************************************************/
/************** Util Functions *************************/
/*******************************************************/

function crawl() {
  var files = DriveApp.searchFiles(
    "(title contains 'design document' or title contains 'tdd')"
    + " and mimeType='application/vnd.google-apps.document'"
    + " and modifiedDate > '2020-01-01T00:00:00'");
  // storeFileIdsInGoogleDoc(files);
  storeFileIdsInFirestore(files)
}

function doWork() {
  // Use LockService to prevent concurrent runs
  const lock = LockService.getScriptLock();
  // wait n minutes to acquire lock and fail if unable to acquire.
  // This prevents unnecessary concurrent runs.
  const minutesToWaitForLock = .5;
  lock.waitLock(minutesToWaitForLock * 60 * 1000); // milliseconds input
  const numFilesPerInvocation = 1;
  const document = getFirestoreDocument()
  const documentValues = document.documents[0].fields.ids.arrayValue.values;
  let fileIds = [];
  if (documentValues) {
    for (const v of documentValues) {
      fileIds.push(v.stringValue);
    }
    const fileIdsToProcess = fileIds.slice(0, numFilesPerInvocation);
    for (const fileId of fileIdsToProcess) {
      exportFileImagesToBucket(fileId);
    }
    writeFirestoreDocument(fileIds.slice(numFilesPerInvocation, fileIds.length))
    lock.releaseLock()
    return fileIdsToProcess;
  } else {
    lock.releaseLock()
    return "No file IDs to parse.";
  }
}

function storeFileIdsInGoogleDoc(files) {
  let filesMap = {}
  while (files.hasNext()) {
    const file = files.next();
    filesMap[file.getId()] = file.getName();
  }
  uploadFileToDrive(Object.keys(filesMap).join("\n"));
  Logger.log(Object.keys(filesMap).length);
}

function extractImagesFromZip(fileBlobZip) {
  const unZipped = Utilities.unzip(fileBlobZip);
  let imageBlobs = []
  for (unzippedFileBlob of unZipped) {
    if (unzippedFileBlob.getContentType().includes("image")) {
      imageBlobs.push(unzippedFileBlob)
    }
  }
  return imageBlobs
}

/*******************************************************/
/************** Cloud Storage Functions ****************/
/*******************************************************/

function exportFileImagesToBucket(fileId, bucket = "psotddimages") {
  const fileBlobZip = exportFileToZip(fileId);
  const imageBlobs = extractImagesFromZip(fileBlobZip);
  for (const imageBlob of imageBlobs) {
    const imageBlobName = imageBlob.getName().replace("images/", "");
    uploadFileToBucket(imageBlob.getContentType(), imageBlob.getBytes(), `${fileId}/${imageBlobName}`, bucket)
  }
}

function uploadFileToBucket(fileContentType, fileContents, fileName, bucket) {
  Logger.log(fileName);
  // replace forward slash with unicode equivalent to prevent folder creation in cloud storage
  fileName = encodeURIComponent(fileName.replace(/\//g, '\u2215'));
  const url = `https://storage.googleapis.com/upload/storage/v1/b/${bucket}/o?uploadType=media&name=images_since_2020/${fileName}`;
  return UrlFetchApp.fetch(url, {
    method: 'post',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    contentType: fileContentType,
    payload: fileContents,
    muteHttpExceptions: true
  });
}

/*******************************************************/
/************** Drive Functions ************************/
/*******************************************************/

function uploadFileToDrive(fileContents) {
  const url = `https://www.googleapis.com/upload/drive/v3/files?uploadType=media`;
  return UrlFetchApp.fetch(url, {
    method: 'post',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    contentType: 'text/plain',
    payload: fileContents
  });
}

function exportFileToZip(fileId = '1aqp67jALbS69GlhgfUq8t4r5YtvGcU6gEY796quX2vY') {
  const url = `https://www.googleapis.com/drive/v3/files/${fileId}/export?mimeType=application/zip`;
  response = UrlFetchApp.fetch(url, {
    method: 'get',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    contentType: 'text/plain;charset=UTF-8',
    muteHttpExceptions: true
  });
  const fileBlobZip = Utilities.newBlob(response.getContent(), "application/zip", fileId);
  return fileBlobZip
}

/*******************************************************/
/************** Firestore Functions ********************/
/*******************************************************/

function storeFileIdsInFirestore(files) {
  let filesMap = {}
  while (files.hasNext()) {
    const file = files.next();
    filesMap[file.getId()] = file.getName();
  }
  Logger.log(Object.keys(filesMap).length);
  writeFirestoreDocument(Object.keys(filesMap));
}

function writeFirestoreDocument(fileIds = ["hello"]) {
  fileIdsArray = []
  for (const fileId of fileIds) {
    fileIdsArray.push({ "stringValue": fileId })
  }
  const url = `https://firestore.googleapis.com/v1/projects/pso-starter-kit/databases/(default)/documents:commit`;
  return UrlFetchApp.fetch(url, {
    method: 'post',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    contentType: 'application/json',
    payload: JSON.stringify({
      "writes": [{
        "update": {
          "name": "projects/pso-starter-kit/databases/(default)/documents/tdds/fileIds",
          "fields": {
            "ids": { "arrayValue": { "values": fileIdsArray } }
          }
        }
      }],
    }),
  });
}

function getFirestoreDocument() {
  const url = `https://firestore.googleapis.com/v1/projects/pso-starter-kit/databases/(default)/documents/tdds`;
  return JSON.parse(UrlFetchApp.fetch(url, {
    method: 'get',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    contentType: 'application/json'
  }));
}

// function createFirestoreDocument(fileIds) {
//   fileIdsArray = []
//   for (const fileId of fileIds) {
//     fileIdsArray.push({ "stringValue": fileId })
//   }
//   const url = `https://firestore.googleapis.com/v1/projects/pso-starter-kit/databases/(default)/documents/fileId?documentId=fileIds`;
//   return UrlFetchApp.fetch(url, {
//     method: 'post',
//     headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
//     contentType: 'application/json',
//     payload: JSON.stringify({
//       "fields": {
//         "ids": { "arrayValue": { "values": fileIdsArray } }
//       },
//     }),
//   });
// }
