from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(); username = serializers.CharField(); email = serializers.CharField()
    first_name = serializers.CharField(); last_name = serializers.CharField(); role = serializers.CharField()
    branch = serializers.IntegerField(source="branch_id"); branch_name = serializers.CharField(source="branch.name", default=None)

class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data

class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

@api_view(["GET"])
def me(request):
    return Response(UserSerializer(request.user).data)
