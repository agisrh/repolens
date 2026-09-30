class TruckRemoteDatasource {
  static TcHttp apiService = TcHttp(baseUrl: Env.baseUrlCoins());

  Future<BaseResponse> getTrucks({int? configId}) async {
    final queryParams = <String, String>{'id': '$configId'};
    final queryString = Uri(queryParameters: queryParams).query;
    const path = 'trucks';
    final finalPath = queryString.isNotEmpty ? '$path?$queryString' : path;
    var response = await apiService.call(finalPath, method: MethodRequest.GET);
    return response;
  }

  Future<BaseResponse> detail(String outletId, int id) async {
    var response = await apiService.call('agen/$outletId/profile/${id}', method: MethodRequest.GET);
    return response;
  }

  Future<BaseResponse> assign(String number) async {
    var response = await apiService.call(
      'assign-truck/assignment',
      method: MethodRequest.PUT,
      request: {'idAssignTruck': number},
    );
    return response;
  }
}
